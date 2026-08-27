import { uniqueStrings } from "./support.mjs";
import {
  boundedRecord,
  dateBefore,
  dateToday,
  invalid,
  isoDate,
  optionalText,
  provenance,
  readJson,
  requiredText,
} from "./finance-shared.mjs";

export const REGULATORY_SOURCES = ["sec_xbrl", "fdic", "cftc"];

export const REGULATORY_INTERVALS = {
  sec_xbrl: 150,
  fdic: 250,
  cftc: 500,
};

export const REGULATORY_DEADLINES = {
  sec_xbrl: 12_000,
  fdic: 12_000,
  cftc: 12_000,
};

function paddedCik(value) {
  return requiredText(value, "cik", /^\d{1,10}$/, 10).padStart(10, "0");
}

async function secXbrl(service, args, maximum, options) {
  const mode = args.xbrl_mode === "frame" ? "frame" : "company_concept";
  const taxonomy = requiredText(
    args.taxonomy ?? "us-gaap",
    "taxonomy",
    /^[A-Za-z0-9_-]{2,40}$/,
    40,
  );
  const concept = requiredText(
    args.concept,
    "concept",
    /^[A-Za-z][A-Za-z0-9_-]{1,119}$/,
    120,
  );
  let url;
  if (mode === "frame") {
    const unit = requiredText(
      args.unit ?? "USD",
      "unit",
      /^[A-Za-z0-9_-]+(?:-per-[A-Za-z0-9_-]+)?$/,
      80,
    );
    const frame = requiredText(
      args.xbrl_period,
      "xbrl_period",
      /^CY\d{4}(?:Q[1-4]I?)?$/,
      10,
    );
    url = `https://data.sec.gov/api/xbrl/frames/${taxonomy}/${concept}/${unit}/${frame}.json`;
  } else {
    const cik = paddedCik(args.cik);
    url = `https://data.sec.gov/api/xbrl/companyconcept/CIK${cik}/${taxonomy}/${concept}.json`;
  }
  const value = await readJson(
    service,
    {
      url,
      accept: "application/json",
      headers: { "User-Agent": service.secUserAgent },
      max_chars: 1_000_000,
      cache_namespace: `finance-sec-xbrl-${mode}`,
      attempts: 1,
    },
    options,
  );
  if (mode === "frame")
    return {
      source: "sec_xbrl",
      mode,
      taxonomy,
      concept,
      label: String(value.label ?? "").slice(0, 500),
      description: String(value.description ?? "").slice(0, 500),
      records: (value.data ?? [])
        .slice(0, maximum)
        .map((record) =>
          boundedRecord(record, [
            "accn",
            "cik",
            "entityName",
            "loc",
            "start",
            "end",
            "val",
            "fy",
            "fp",
            "form",
            "filed",
            "frame",
          ]),
        ),
      provenance: provenance("U.S. Securities and Exchange Commission", url),
    };
  const facts = Object.entries(value.units ?? {})
    .flatMap(([unit, entries]) =>
      entries.map((entry) => ({
        unit: unit.slice(0, 80),
        ...boundedRecord(entry, [
          "start",
          "end",
          "val",
          "accn",
          "fy",
          "fp",
          "form",
          "filed",
          "frame",
        ]),
      })),
    )
    .sort((left, right) =>
      String(right.filed).localeCompare(String(left.filed)),
    )
    .slice(0, maximum);
  return {
    source: "sec_xbrl",
    mode,
    cik: value.cik,
    entity: String(value.entityName ?? "").slice(0, 500),
    taxonomy: value.taxonomy ?? taxonomy,
    concept: value.tag ?? concept,
    label: String(value.label ?? "").slice(0, 500),
    description: String(value.description ?? "").slice(0, 500),
    facts,
    provenance: provenance("U.S. Securities and Exchange Commission", url),
  };
}

const FDIC_DATASETS = {
  institutions: {
    fields: ["NAME", "CERT", "CITY", "STNAME", "ACTIVE", "ASSET", "DEP"],
    sort: "ASSET",
  },
  financials: {
    fields: ["CERT", "REPDTE", "ASSET", "DEP", "NETINC", "EQ"],
    sort: "REPDTE",
  },
  failures: {
    fields: ["NAME", "CERT", "CITYST", "FAILDATE", "SAVR", "RESTYPE"],
    sort: "FAILDATE",
  },
  summary: {
    fields: ["YEAR", "STNAME", "NUMINS", "ASSET", "DEP", "NETINC"],
    sort: "YEAR",
  },
};

async function fdic(service, args, maximum, options) {
  const dataset = FDIC_DATASETS[args.dataset] ? args.dataset : "institutions";
  const configured = FDIC_DATASETS[dataset];
  const requestedFields = uniqueStrings(args.fields, 20, 40).map((field) =>
    field.toUpperCase(),
  );
  if (requestedFields.some((field) => !/^[A-Z][A-Z0-9_]{0,39}$/.test(field)))
    throw invalid("FDIC fields must be valid API field names");
  const fields = requestedFields.length ? requestedFields : configured.fields;
  const filter = optionalText(
    args.fdic_filter,
    "fdic_filter",
    /^[A-Za-z0-9_:\s"'!()[\]{}.*+,-]{1,300}$/,
    300,
  );
  const url = new URL(`https://api.fdic.gov/banks/${dataset}`);
  if (filter) url.searchParams.set("filters", filter);
  url.searchParams.set("fields", fields.join(","));
  url.searchParams.set("limit", String(maximum));
  url.searchParams.set("offset", "0");
  url.searchParams.set("sort_by", configured.sort);
  url.searchParams.set("sort_order", "DESC");
  const value = await readJson(
    service,
    {
      url: url.href,
      accept: "application/json",
      max_chars: 750_000,
      cache_namespace: `finance-fdic-${dataset}`,
      attempts: 2,
    },
    options,
  );
  return {
    source: "fdic",
    dataset,
    records: (value.data ?? [])
      .slice(0, maximum)
      .map((item) => boundedRecord(item.data ?? item, fields)),
    metadata: value.meta ?? {},
    totals: value.totals ?? {},
    provenance: provenance("Federal Deposit Insurance Corporation", url.href),
  };
}

const CFTC_REPORTS = {
  legacy_futures: {
    id: "6dca-aqww",
    fields: [
      "noncomm_positions_long_all",
      "noncomm_positions_short_all",
      "comm_positions_long_all",
      "comm_positions_short_all",
    ],
  },
  legacy_combined: {
    id: "jun7-fc8e",
    fields: [
      "noncomm_positions_long_all",
      "noncomm_positions_short_all",
      "comm_positions_long_all",
      "comm_positions_short_all",
    ],
  },
  disaggregated_futures: {
    id: "72hh-3qpy",
    fields: [
      "prod_merc_positions_long",
      "prod_merc_positions_short",
      "swap_positions_long_all",
      "swap__positions_short_all",
      "m_money_positions_long_all",
      "m_money_positions_short_all",
    ],
  },
  tff_futures: {
    id: "gpe5-46if",
    fields: [
      "dealer_positions_long_all",
      "dealer_positions_short_all",
      "asset_mgr_positions_long",
      "asset_mgr_positions_short",
      "lev_money_positions_long",
      "lev_money_positions_short",
    ],
  },
};

function soqlLiteral(value) {
  return value.replaceAll("'", "''");
}

async function cftc(service, args, maximum, options) {
  const report = CFTC_REPORTS[args.cftc_report]
    ? args.cftc_report
    : "tff_futures";
  const configured = CFTC_REPORTS[report];
  const fromDate = isoDate(args.from_date, dateBefore(365));
  const toDate = isoDate(args.to_date, dateToday());
  if (fromDate > toDate)
    throw invalid(
      "from_date must not exceed to_date",
      "alta_finance_invalid_date_range",
    );
  const market = optionalText(
    args.market,
    "market",
    /^[A-Za-z0-9\s#&/().,'+_-]{1,100}$/,
    100,
  );
  const commonFields = [
    "market_and_exchange_names",
    "report_date_as_yyyy_mm_dd",
    "commodity_name",
    "open_interest_all",
  ];
  const url = new URL(
    `https://publicreporting.cftc.gov/resource/${configured.id}.json`,
  );
  url.searchParams.set(
    "$select",
    [...commonFields, ...configured.fields].join(","),
  );
  const clauses = [
    `report_date_as_yyyy_mm_dd between '${fromDate}T00:00:00.000' and '${toDate}T23:59:59.999'`,
  ];
  if (market)
    clauses.push(
      `upper(market_and_exchange_names) like '%${soqlLiteral(market.toUpperCase())}%'`,
    );
  url.searchParams.set("$where", clauses.join(" AND "));
  url.searchParams.set("$order", "report_date_as_yyyy_mm_dd DESC");
  url.searchParams.set("$limit", String(maximum));
  const records = await readJson(
    service,
    {
      url: url.href,
      accept: "application/json",
      max_chars: 750_000,
      cache_namespace: `finance-cftc-${report}`,
      attempts: 1,
    },
    options,
  );
  return {
    source: "cftc",
    report,
    records: records
      .slice(0, maximum)
      .map((record) =>
        boundedRecord(record, [...commonFields, ...configured.fields]),
      ),
    provenance: provenance("Commodity Futures Trading Commission", url.href),
  };
}

export const REGULATORY_ADAPTERS = { sec_xbrl: secXbrl, fdic, cftc };
