// FEC export (report JS), run with: node --test erpnext_france/tests/js/
// The report script is loaded with stand-ins for frappe, moment, $ and the DOM.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const SCRIPT = new URL(
  "../../erpnext_france/report/fichier_des_ecritures_comptables_[fec]/fichier_des_ecritures_comptables_[fec].js",
  import.meta.url
);

const COLUMNS = [
  "JournalCode",
  "JournalLib",
  "EcritureNum",
  "EcritureDate",
  "CompteNum",
  "CompteLib",
  "CompAuxNum",
  "CompAuxLib",
  "PieceRef",
  "PieceDate",
  "EcritureLib",
  "Debit",
  "Credit",
  "EcritureLet",
  "DateLet",
  "ValidDate",
  "Montantdevise",
  "Idevise",
  "DateLimitReglmt",
  "NumFacture",
  "ExportDate",
  "GlName",
];

function load() {
  const downloads = [];
  const values = {
    Company: { siret: "12345678900011" },
    "Fiscal Year": { year_end_date: "2026-12-31" },
  };
  const frappe = {
    query_reports: {},
    defaults: { get_user_default: () => null },
    datetime: { get_today: () => "2026-09-26", add_months: (date) => date },
    db: {
      get_value: (doctype, name, field, callback) => callback(values[doctype]),
    },
    msgprint: (message) => downloads.push({ message }),
    call: () => {},
  };
  const erpnext = { utils: { get_fiscal_year: () => "2026" } };
  const moment = (date) => ({ format: () => date.replaceAll("-", "") });
  const $ = { each: (rows, fn) => rows.forEach((row, i) => fn(i, row)) };
  const document = {
    createElement: () => ({
      download: "",
      click() {
        downloads.push({ filename: this.download, blob: this.blob });
      },
      set href(value) {
        this.blob = value;
      },
    }),
    body: { appendChild() {}, removeChild() {} },
  };
  const URL = { createObjectURL: (blob) => blob };
  const source = readFileSync(SCRIPT, "utf8");
  const exports = new Function(
    "frappe",
    "erpnext",
    "__",
    "moment",
    "$",
    "document",
    "URL",
    "has_common",
    `${source}\nreturn { fec_export };`
  )(
    frappe,
    erpnext,
    (s) => s,
    moment,
    $,
    document,
    URL,
    () => true
  );
  return { ...exports, downloads };
}

function report(rows) {
  return {
    get_values: () => ({ company: "HCO", fiscal_year: "2026" }),
    columns: COLUMNS.map((fieldname) => ({ fieldname })),
    get_data_for_csv: () => rows.map((row) => [...row]),
  };
}

function row(overrides = {}) {
  const values = Object.fromEntries(COLUMNS.map((c) => [c, c.toLowerCase()]));
  return COLUMNS.map((c) => overrides[c] ?? values[c]);
}

test("the file is named after the SIREN, not the SIRET", () => {
  const { fec_export, downloads } = load();
  fec_export(report([row()]), false);
  assert.match(downloads[0].filename, /^123456789FEC20261231\./);
});

test("fields are separated by tabs, and a field cannot break a line or a column", async () => {
  const { fec_export, downloads } = load();
  fec_export(
    report([
      row({
        EcritureLib: "Achat; lot\t2\nsuite",
        CompAuxLib: "Dupont & Fils; SARL",
      }),
    ]),
    false
  );
  const lines = (await downloads[0].blob.text()).split("\n");
  assert.equal(lines.length, 2);
  const [header, first] = lines.map((line) => line.split("\t"));
  assert.equal(header.length, 18);
  assert.equal(first.length, header.length);
  assert.equal(first[header.indexOf("EcritureLib")], "Achat; lot 2 suite");
  assert.equal(first[header.indexOf("CompAuxLib")], "Dupont & Fils; SARL");
});

test("the file holds exactly the 18 regulatory fields, as a .txt flat file", async () => {
  const { fec_export, downloads } = load();
  fec_export(report([row()]), false);
  assert.match(downloads[0].filename, /\.txt$/);
  const header = new TextDecoder("latin1")
    .decode(await downloads[0].blob.arrayBuffer())
    .split("\n")[0]
    .split("\t");
  assert.deepEqual(header, COLUMNS.slice(0, 18));
});

test("the file is encoded in ISO-8859-15", async () => {
  const { fec_export, downloads } = load();
  fec_export(report([row({ EcritureLib: "Café 12 €" })]), false);
  const bytes = new Uint8Array(await downloads[0].blob.arrayBuffer());
  const text = Array.from(bytes);
  assert.ok(text.includes(0xe9), "é is 0xE9");
  assert.ok(text.includes(0xa4), "€ is 0xA4 in ISO-8859-15");
  assert.ok(!text.includes(0xc3), "no UTF-8 multi-byte sequence");
});
