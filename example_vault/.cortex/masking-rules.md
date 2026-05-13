# Content Masking Rules — Taiwan Banking PII

These rules redact personally identifiable information (PII) for
Taiwanese banking customers before content is sent to LLM enrichment
or written to the wiki. All ingested documents are subject to these
rules when masking is enabled.

Applicable regulations: Taiwan Personal Data Protection Act (PDPA / 個人資料保護法),
Financial Supervisory Commission (FSC / 金管會) guidelines, and banking
secrecy obligations under the Banking Act (銀行法).

## National ID Numbers

Mask Taiwan national identification numbers (身分證字號).
Format: one uppercase letter followed by 9 digits (e.g., A123456789).
The leading letter encodes the place of initial household registration.
Replace with `[NATIONAL_ID]`.

### Patterns
- `[A-Z][12]\d{8}`

## Resident Certificate Numbers

Mask Alien Resident Certificate (ARC) and permanent resident numbers (居留證號).
Old format: two letters followed by 8 digits. New format (2021+): same as
national ID — one letter followed by 8 digits and a check digit starting with 8 or 9.
Replace with `[RESIDENT_ID]`.

### Patterns
- `[A-Z]{2}\d{8}`

## Unified Business Numbers

Mask unified business numbers (統一編號 / 統編) used to identify
companies and business entities registered in Taiwan. Format: exactly 8 digits,
often prefixed with context like "統編" or "UBN".
Replace with `[BUSINESS_ID]`.

### Patterns
- `統編[：:\s]*\d{8}`
- `UBN[：:\s]*\d{8}`

## Bank Account Numbers

Mask bank account numbers. Taiwan domestic accounts are typically
12–16 digits, sometimes grouped with dashes. International wire
transfers may include SWIFT/BIC codes. Replace with `[ACCOUNT_NUMBER]`.

### Patterns
- `\d{3}-\d{2}-\d{6,8}-\d{1}`
- `\d{12,16}`
- `SWIFT[：:\s]*[A-Z]{6}[A-Z0-9]{2}([A-Z0-9]{3})?`

## Credit Card Numbers

Mask credit card numbers (信用卡號). Typically 16 digits, displayed
in groups of four separated by spaces or dashes.
Replace with `[CREDIT_CARD]`.

### Patterns
- `\d{4}[-\s]\d{4}[-\s]\d{4}[-\s]\d{4}`
- `[45]\d{15}`

## Phone Numbers

Mask Taiwan phone numbers including mobile (09xx) and landline formats.
Mobile numbers: 09xx-xxx-xxx or 09xxxxxxxx (10 digits starting with 09).
Landline: area code (02–08) followed by 7–8 digits, with or without dashes.
Replace with `[PHONE]`.

### Patterns
- `09\d{2}[-\s]?\d{3}[-\s]?\d{3}`
- `0[2-8][-\s]?\d{3,4}[-\s]?\d{3,4}`
- `\+886[-\s]?9\d{2}[-\s]?\d{3}[-\s]?\d{3}`

## Email Addresses

Mask all email addresses found in customer data.
Replace with `[EMAIL]`.

### Patterns
- `[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}`

## Postal Addresses

Mask full postal addresses in Taiwan format (台灣地址). These typically
start with a 3- or 5-digit postal code followed by city/county (縣市),
district (鄉鎮市區), and street details. Also mask romanized addresses.
Replace with `[ADDRESS]`.

The LLM should recognize and mask full addresses even when they don't
match a simple regex — for example "台北市信義區松仁路100號12樓" or
"12F, No. 100, Songren Rd., Xinyi Dist., Taipei City".

### Patterns
- `(?:^|(?<=\s))\d{3}[-\s]?\d{2}(?=\s|$)`
- `\d{3,5}\s*[^\d\s]{2,}[縣市][^\d\s]*[鄉鎮市區][^\d\s]*[路街道巷弄號樓]\S*`

## Date of Birth

Mask dates of birth (出生日期). Taiwan uses both the Minguo/ROC calendar
(e.g., 民國 85 年 3 月 15 日 = 1996-03-15) and the Gregorian calendar.
Replace with `[DATE_OF_BIRTH]`.

The LLM should identify dates of birth from context (e.g., "born on",
"出生日期", "生日", "DOB") even when the date format alone is ambiguous.

### Patterns
- `民國\s?\d{2,3}\s?年\s?\d{1,2}\s?月\s?\d{1,2}\s?日`
- `\d{4}[-/]\d{1,2}[-/]\d{1,2}`

## Customer Names

Mask customer names — both Chinese names (typically 2–4 characters) and
romanized names. Replace Chinese names with `[CUSTOMER_NAME]` and
romanized names with `[CUSTOMER_NAME]`.

The LLM should identify names from context: fields like "姓名", "客戶",
"戶名", "持卡人", "Name", "Account Holder", salutations (先生/小姐/女士),
or names appearing alongside other PII (e.g., next to an ID number or
account number). Do not mask names of public figures, companies, or
place names.

## Passport Numbers

Mask passport numbers (護照號碼). Taiwan passport numbers consist of
a single digit followed by 8 digits (total 9 digits). Some older formats
may have a letter prefix.
Replace with `[PASSPORT]`.

### Patterns
- `[A-Z]?\d{9}`

## Income and Financial Amounts

Mask specific income figures, salary amounts, loan values, transaction
amounts, and account balances when they appear in the context of individual
customer data. Replace with `[FINANCIAL_AMOUNT]`.

Preserve aggregate or statistical figures that are not tied to an
identifiable individual (e.g., "average loan size" or "total portfolio
value" are acceptable).

### Patterns
- `NT\$\s?[\d,]+(\.\d{1,2})?`
- `TWD\s?[\d,]+(\.\d{1,2})?`
- `新?臺幣\s?[\d,]+(\.\d{1,2})?\s?元`
