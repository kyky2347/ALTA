import { boundedInteger, uniqueStrings } from "./support.mjs";
import {
  assertRange,
  assertPeriodRange,
  boundedRecord,
  compactRecord,
  dateBefore,
  dateToday,
  invalid,
  isoDate,
  period,
  provenance,
  readCsv,
  readJson,
  requiredText,
} from "./finance-shared.mjs";

export const MACRO_SOURCES = ["fred", "bls", "nyfed", "ecb", "imf", "oecd"];

export const MACRO_INTERVALS = {
  fred: 250,
  bls: 500,
  nyfed: 250,
  ecb: 250,
  imf: 500,
  oecd: 500,
};

export const MACRO_DEADLINES = {
  fred: 10_000,
  bls: 10_000,
  nyfed: 10_000,
  ecb: 12_000,
  imf: 20_000,
  oecd: 15_000,
};

async function fred(service, args, maximum, options) {
  const series = requiredText(
    args.series_id ?? args.indicator,
    "series_id",
    /^[A-Za-z0-9._-]{1,80}$/,
    80,
  ).toUpperCase();
  const fromDate = isoDate(args.from_date, dateBefore(365 * 5));
  const toDate = isoDate(args.to_date, dateToday());
  assertRange(fromDate, toDate);
  const url = new URL("https://fred.stlouisfed.org/graph/fredgraph.csv");
  url.searchParams.set("id", series);
  url.searchParams.set("cosd", fromDate);
  url.searchParams.set("coed", toDate);
  const rows = await readCsv(
    service,
    {
      url: url.href,
      accept: "text/csv",
      max_chars: 512_000,
      cache_namespace: "finance-fred",
      attempts: 2,
    },
    maximum,
    options,
  );
  return {
    source: "fred",
    series_id: series,
    observations: rows.map((row) => ({
      date: row.observation_date,
      value: row[series],
    })),
    provenance: provenance("Federal Reserve Bank of St. Louis", url.href),
  };
}

async function bls(service, args, maximum, options) {
  const series = requiredText(
    args.series_id,
    "series_id",
    /^[A-Za-z0-9_-]{2,80}$/,
    80,
  ).toUpperCase();
  const url = `https://api.bls.gov/publicAPI/v1/timeseries/data/${encodeURIComponent(series)}`;
  const value = await readJson(
    service,
    {
      url,
      accept: "application/json",
      max_chars: 512_000,
      cache_namespace: "finance-bls",
      attempts: 1,
    },
    options,
  );
  if (value.status !== "REQUEST_SUCCEEDED")
    throw Object.assign(
      new Error(value.message?.join("; ") || "BLS returned no public data"),
      { status: 502, code: "alta_finance_bls_unavailable" },
    );
  const result = value.Results?.series?.[0] ?? {};
  return {
    source: "bls",
    series_id: result.seriesID ?? series,
    observations: (result.data ?? []).slice(0, maximum).map((item) => ({
      year: item.year,
      period: item.period,
      period_name: item.periodName,
      value: item.value,
      latest: item.latest === "true",
      footnotes: (item.footnotes ?? [])
        .map((note) => note.text)
        .filter(Boolean),
    })),
    provenance: provenance("U.S. Bureau of Labor Statistics", url),
  };
}

function nyFedPath(rateType) {
  if (["tgcr", "bgcr", "sofr", "sofrai"].includes(rateType))
    return `secured/${rateType}`;
  if (["effr", "obfr"].includes(rateType)) return `unsecured/${rateType}`;
  return "all";
}

async function nyFed(service, args, maximum, options) {
  const rateType = [
    "all",
    "tgcr",
    "bgcr",
    "sofr",
    "sofrai",
    "effr",
    "obfr",
  ].includes(args.rate_type)
    ? args.rate_type
    : "all";
  const fromDate = isoDate(args.from_date, dateBefore(30));
  const toDate = isoDate(args.to_date, dateToday());
  assertRange(fromDate, toDate);
  const url = new URL(
    `https://markets.newyorkfed.org/api/rates/${nyFedPath(rateType)}/search.json`,
  );
  url.searchParams.set("startDate", fromDate);
  url.searchParams.set("endDate", toDate);
  url.searchParams.set("type", "rate");
  const value = await readJson(
    service,
    {
      url: url.href,
      accept: "application/json",
      max_chars: 512_000,
      cache_namespace: "finance-nyfed-rates",
      attempts: 2,
    },
    options,
  );
  return {
    source: "nyfed",
    rate_type: rateType,
    rates: (value.refRates ?? [])
      .slice(0, maximum)
      .map((rate) =>
        boundedRecord(rate, [
          "effectiveDate",
          "type",
          "percentRate",
          "average30day",
          "average90day",
          "average180day",
          "index",
          "volumeInBillions",
          "targetRateFrom",
          "targetRateTo",
          "percentPercentile1",
          "percentPercentile25",
          "percentPercentile75",
          "percentPercentile99",
          "revisionIndicator",
        ]),
      ),
    provenance: provenance("Federal Reserve Bank of New York", url.href),
  };
}

async function ecb(service, args, maximum, options) {
  const dataflow = requiredText(
    args.dataflow,
    "dataflow",
    /^[A-Za-z0-9_.@-]{1,100}$/,
    100,
  );
  const key = requiredText(args.key, "key", /^[A-Za-z0-9._+@-]{1,300}$/, 300);
  const fromPeriod = period(
    args.from_period,
    String(new Date().getUTCFullYear() - 5),
  );
  const toPeriod = period(args.to_period, dateToday());
  assertPeriodRange(fromPeriod, toPeriod);
  const url = new URL(
    `https://data-api.ecb.europa.eu/service/data/${encodeURIComponent(dataflow)}/${encodeURIComponent(key)}`,
  );
  url.searchParams.set("startPeriod", fromPeriod);
  url.searchParams.set("endPeriod", toPeriod);
  url.searchParams.set("format", "csvdata");
  const rows = await readCsv(
    service,
    {
      url: url.href,
      accept: "text/csv",
      max_chars: 750_000,
      cache_namespace: "finance-ecb-sdmx",
      attempts: 2,
    },
    maximum,
    options,
  );
  return {
    source: "ecb",
    dataflow,
    key,
    observations: rows.map((row) => ({
      key: row.KEY,
      period: row.TIME_PERIOD,
      value: row.OBS_VALUE,
      status: row.OBS_STATUS,
      title: row.TITLE_COMPL ?? row.TITLE,
      unit: row.UNIT,
      frequency: row.FREQ,
    })),
    provenance: provenance("European Central Bank", url.href),
  };
}

function selectedCountries(args) {
  const candidates = args.countries?.length ? args.countries : [args.country];
  const countries = uniqueStrings(candidates, 10, 12).map((value) =>
    value.toUpperCase(),
  );
  if (
    !countries.length ||
    countries.some((value) => !/^[A-Z0-9]{2,12}$/.test(value))
  )
    throw invalid("IMF requires valid country, region, or group codes");
  return countries;
}

async function imf(service, args, maximum, options) {
  const indicator = requiredText(
    args.indicator,
    "indicator",
    /^[A-Za-z0-9_.-]{1,80}$/,
    80,
  ).toUpperCase();
  const countries = selectedCountries(args);
  const currentYear = new Date().getUTCFullYear();
  const fromYear = boundedInteger(args.from_year, currentYear - 5, 1800, 2200);
  const toYear = boundedInteger(args.to_year, currentYear + 5, 1800, 2200);
  assertRange(fromYear, toYear, "year");
  const years = Array.from(
    { length: toYear - fromYear + 1 },
    (_, index) => fromYear + index,
  );
  const url = new URL(
    `https://www.imf.org/external/datamapper/api/v2/${encodeURIComponent(indicator)}/${countries.map(encodeURIComponent).join("/")}`,
  );
  url.searchParams.set("periods", years.join(","));
  const value = await readJson(
    service,
    {
      url: url.href,
      accept: "application/json",
      max_chars: 1_000_000,
      cache_namespace: "finance-imf-datamapper",
      attempts: 1,
    },
    options,
  );
  const series = value.values?.[indicator] ?? {};
  const observations = countries
    .flatMap((country) =>
      years.map((yearValue) => ({
        country,
        year: yearValue,
        value: series[country]?.[yearValue] ?? null,
      })),
    )
    .filter((item) => item.value !== null)
    .slice(0, maximum);
  return {
    source: "imf",
    indicator: value.indicators?.[indicator]
      ? boundedRecord(value.indicators[indicator], [
          "label",
          "description",
          "source",
          "unit",
          "dataset",
          "projection-year",
          "last-modified",
        ])
      : { id: indicator },
    observations,
    provenance: provenance("International Monetary Fund", url.href),
  };
}

async function oecd(service, args, maximum, options) {
  const dataflow = requiredText(
    args.dataflow,
    "dataflow",
    /^[A-Za-z0-9_.@,-]{3,180}$/,
    180,
  );
  const key = requiredText(args.key, "key", /^[A-Za-z0-9._+@-]{1,300}$/, 300);
  if (key.toLowerCase() === "all")
    throw invalid("OECD queries must use a bounded SDMX key instead of all");
  const fromPeriod = period(
    args.from_period,
    String(new Date().getUTCFullYear() - 5),
  );
  const toPeriod = period(args.to_period, dateToday());
  assertPeriodRange(fromPeriod, toPeriod);
  const url = new URL(
    `https://sdmx.oecd.org/public/rest/v1/data/${dataflow}/${key}`,
  );
  url.searchParams.set("startPeriod", fromPeriod);
  url.searchParams.set("endPeriod", toPeriod);
  url.searchParams.set("dimensionAtObservation", "AllDimensions");
  url.searchParams.set("format", "csvfilewithlabels");
  const records = await readCsv(
    service,
    {
      url: url.href,
      accept: "text/csv",
      headers: { "Accept-Language": "en" },
      max_chars: 1_000_000,
      cache_namespace: "finance-oecd-sdmx",
      attempts: 1,
    },
    maximum,
    options,
  );
  return {
    source: "oecd",
    dataflow,
    key,
    records: records.map((record) => {
      const selected = boundedRecord(record, [
        "REF_AREA",
        "Reference area",
        "FREQ",
        "Frequency of observation",
        "MEASURE",
        "Measure",
        "UNIT_MEASURE",
        "Unit of measure",
        "Adjustment",
        "Transformation",
        "TIME_PERIOD",
        "Time period",
        "OBS_VALUE",
        "Observation value",
        "OBS_STATUS",
        "Observation status",
      ]);
      return compactRecord({
        reference_area_code: selected.REF_AREA,
        reference_area: selected["Reference area"],
        frequency_code: selected.FREQ,
        frequency: selected["Frequency of observation"],
        measure_code: selected.MEASURE,
        measure: selected.Measure,
        unit_code: selected.UNIT_MEASURE,
        unit: selected["Unit of measure"],
        adjustment: selected.Adjustment,
        transformation: selected.Transformation,
        period: selected.TIME_PERIOD ?? selected["Time period"],
        value: selected.OBS_VALUE ?? selected["Observation value"],
        status: selected.OBS_STATUS ?? selected["Observation status"],
      });
    }),
    provenance: provenance(
      "Organisation for Economic Co-operation and Development",
      url.href,
    ),
  };
}

export const MACRO_ADAPTERS = { fred, bls, nyfed: nyFed, ecb, imf, oecd };
