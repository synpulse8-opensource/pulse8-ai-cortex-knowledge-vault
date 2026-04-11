import { createServer } from "node:http";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { readdirSync } from "node:fs";

const exec = promisify(execFile);
const PORT = parseInt(process.env.QMD_PORT || "3100", 10);
const VAULT_PATH = process.env.VAULT_PATH || "/vault";
const QMD_BIN = process.env.QMD_BIN || "qmd";

let setupReady = false;

async function qmd(args, timeout = 120_000) {
  const { stdout, stderr } = await exec(QMD_BIN, args, {
    timeout,
    maxBuffer: 10 * 1024 * 1024,
  });
  return { stdout: stdout.trim(), stderr: stderr.trim() };
}

async function runSetup() {
  const subdirs = [];
  try {
    for (const entry of readdirSync(VAULT_PATH, { withFileTypes: true })) {
      if (entry.isDirectory() && !entry.name.startsWith(".")) {
        subdirs.push(entry.name);
      }
    }
  } catch {
    console.warn("Cannot read vault directory:", VAULT_PATH);
    return;
  }

  if (subdirs.length === 0) {
    console.warn("Vault is empty — skipping QMD setup");
    return;
  }

  console.log("Setting up QMD collections for:", subdirs.join(", "));

  for (const name of subdirs) {
    try {
      await qmd(["collection", "add", `${VAULT_PATH}/${name}`, "--name", name]);
      console.log(`  collection '${name}' added`);
    } catch (e) {
      if (e.message && e.message.includes("already exists")) {
        console.log(`  collection '${name}' already exists`);
      } else {
        console.warn(`  collection '${name}' failed:`, e.message);
      }
    }
  }

  try {
    await qmd(["context", "add", "qmd://wiki", "Knowledge articles compiled from raw sources"]);
  } catch { /* already exists */ }
  try {
    await qmd(["context", "add", "qmd://agents", "Agent definition files"]);
  } catch { /* already exists */ }

  try {
    await qmd(["update"]);
    console.log("QMD update complete");
  } catch (e) {
    console.warn("QMD update warning:", e.message);
  }

  try {
    await qmd(["embed"], 600_000);
    console.log("QMD embed complete");
  } catch (e) {
    console.warn("QMD embed warning:", e.message);
  }

  setupReady = true;
  console.log("QMD setup finished");
}

async function readBody(req) {
  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  return JSON.parse(Buffer.concat(chunks).toString());
}

function json(res, status, data) {
  res.writeHead(status, { "Content-Type": "application/json" });
  res.end(JSON.stringify(data));
}

const server = createServer(async (req, res) => {
  try {
    if (req.method === "GET" && req.url === "/health") {
      return json(res, 200, { status: "ok", setup_ready: setupReady });
    }

    if (req.method !== "POST") {
      return json(res, 405, { error: "Method not allowed" });
    }

    if (req.url === "/setup") {
      await runSetup();
      return json(res, 200, { status: "ok" });
    }

    if (req.url === "/update") {
      await qmd(["update"]);
      try {
        await qmd(["embed"], 600_000);
      } catch (e) {
        console.warn("embed warning:", e.message);
      }
      return json(res, 200, { status: "ok" });
    }

    if (req.url === "/search") {
      const body = await readBody(req);
      const { query, mode = "hybrid", collection, top_k = 10 } = body;

      if (!query) return json(res, 400, { error: "query required" });

      if (!setupReady) {
        return json(res, 200, []);
      }

      const cmdMap = { keyword: "search", semantic: "vsearch", hybrid: "query" };
      const cmd = cmdMap[mode] || "query";
      const args = [cmd, query, "--json", "-n", String(top_k)];
      if (collection) args.push("-c", collection);

      try {
        const { stdout } = await qmd(args);
        return json(res, 200, JSON.parse(stdout));
      } catch (e) {
        console.warn("Search command failed:", e.message);
        return json(res, 200, []);
      }
    }

    return json(res, 404, { error: "Not found" });
  } catch (e) {
    console.error("Request error:", e.message);
    return json(res, 500, { error: e.message });
  }
});

server.listen(PORT, "0.0.0.0", () => {
  console.log(`QMD HTTP server listening on port ${PORT}`);
  console.log(`Vault path: ${VAULT_PATH}`);
  runSetup().catch((e) => console.error("Auto-setup failed:", e.message));
});
