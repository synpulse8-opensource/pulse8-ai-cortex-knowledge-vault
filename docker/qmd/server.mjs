import { createServer } from "node:http";
import { execFile } from "node:child_process";
import { promisify } from "node:util";

const exec = promisify(execFile);
const PORT = parseInt(process.env.QMD_PORT || "3100", 10);
const VAULT_PATH = process.env.VAULT_PATH || "/vault";
const QMD_BIN = process.env.QMD_BIN || "qmd";

async function qmd(args, timeout = 120_000) {
  const { stdout, stderr } = await exec(QMD_BIN, args, {
    timeout,
    maxBuffer: 10 * 1024 * 1024,
  });
  return { stdout: stdout.trim(), stderr: stderr.trim() };
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
      return json(res, 200, { status: "ok" });
    }

    if (req.method !== "POST") {
      return json(res, 405, { error: "Method not allowed" });
    }

    if (req.url === "/setup") {
      const collections = ["wiki", "agents", "sessions", "daily"];
      const results = [];
      for (const name of collections) {
        try {
          await qmd(["collection", "add", `${VAULT_PATH}/${name}`, "--name", name]);
          results.push({ name, status: "added" });
        } catch {
          results.push({ name, status: "exists" });
        }
      }

      try {
        await qmd(["context", "add", "qmd://wiki", "Knowledge articles compiled from raw sources"]);
      } catch { /* already exists */ }
      try {
        await qmd(["context", "add", "qmd://agents", "Agent definition files"]);
      } catch { /* already exists */ }

      await qmd(["update"]);
      try {
        await qmd(["embed"], 300_000);
      } catch (e) {
        console.warn("embed warning:", e.message);
      }

      return json(res, 200, { status: "ok", collections: results });
    }

    if (req.url === "/update") {
      await qmd(["update"]);
      try {
        await qmd(["embed"], 300_000);
      } catch (e) {
        console.warn("embed warning:", e.message);
      }
      return json(res, 200, { status: "ok" });
    }

    if (req.url === "/search") {
      const body = await readBody(req);
      const { query, mode = "hybrid", collection, top_k = 10 } = body;

      if (!query) return json(res, 400, { error: "query required" });

      const cmdMap = { keyword: "search", semantic: "vsearch", hybrid: "query" };
      const cmd = cmdMap[mode] || "query";
      const args = [cmd, query, "--json", "-n", String(top_k)];
      if (collection) args.push("-c", collection);

      const { stdout } = await qmd(args);
      try {
        return json(res, 200, JSON.parse(stdout));
      } catch {
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
});
