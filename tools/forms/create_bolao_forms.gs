/**
 * Google Apps Script
 * Cria automaticamente o bundle de Forms do bolão para uma nova temporada.
 *
 * Como usar:
 * 1) Abra script.new no Google (Apps Script)
 * 2) Cole este arquivo inteiro
 * 3) Ajuste SEASON_LABEL e PARTICIPANTS
 * 4) Execute createBolaoFormsBundle()
 * 5) Copie o JSON do LOG/aba CONFIG para configurar o frontend
 */

const SEASON_LABEL = "2026-2027";
const PARTICIPANTS = [
  "Leo Picca",
  "Leo Raposo",
  "Serginho",
  "Biel",
  "Rafinha",
  "Ranieri",
  "Nanel",
  "Marcel",
  "Dan",
  "Celsinho",
  "Enrico",
  "Gui Giron",
  "Scarpa",
  "Victor",
  "Faber",
  "Felippe Leite",
  "Muca",
  "Feijão",
  "Ivan",
  "Michel",
  "Deco",
];

const TEAM_OPTIONS = [
  "Real Madrid",
  "Barcelona",
  "Bayern de Munique",
  "Manchester City",
  "Liverpool",
  "Chelsea",
  "Paris Saint-Germain",
  "Arsenal",
  "Internazionale",
  "Juventus",
  "Borussia Dortmund",
  "Benfica",
  "Napoli",
  "Atlético de Madrid",
  "Bayer Leverkusen",
  "Tottenham",
];

function createBolaoFormsBundle() {
  const spreadsheet = SpreadsheetApp.create(`Bolão UEFA • Respostas • ${SEASON_LABEL}`);
  const specs = getFormSpecs();
  const forms = {};

  specs.forEach((spec) => {
    forms[spec.key] = createFormFromSpec(spec, spreadsheet);
  });

  const output = {
    season_label: SEASON_LABEL,
    spreadsheet_id: spreadsheet.getId(),
    spreadsheet_url: spreadsheet.getUrl(),
    forms,
    generated_at: new Date().toISOString(),
  };

  writeConfigSheet(spreadsheet, output);
  Logger.log(JSON.stringify(output, null, 2));
  return output;
}

function createFormFromSpec(spec, spreadsheet) {
  const title = `${spec.title} • ${SEASON_LABEL}`;
  const form = FormApp.create(title);
  form.setDescription(spec.description || "");
  form.setCollectEmail(true);
  form.setAllowResponseEdits(false);
  form.setProgressBar(true);

  const fieldMap = {};

  const participantItem = form.addListItem();
  participantItem.setTitle("Participante");
  participantItem.setChoiceValues(PARTICIPANTS);
  participantItem.setRequired(true);
  fieldMap.participant = `entry.${participantItem.getId()}`;

  spec.fields.forEach((field) => {
    const entryName = `entry.${addFormItem(form, field)}`;
    fieldMap[field.key] = entryName;
  });

  const beforeSheetIds = spreadsheet.getSheets().map((sheet) => sheet.getSheetId());
  form.setDestination(FormApp.DestinationType.SPREADSHEET, spreadsheet.getId());
  Utilities.sleep(1200);

  const responseSheet = resolveResponseSheet(spreadsheet, beforeSheetIds);
  const desiredSheetName = `${spec.key}_RAW`;
  if (responseSheet && responseSheet.getName() !== desiredSheetName) {
    try {
      responseSheet.setName(desiredSheetName);
    } catch (error) {
      // Em caso de nome duplicado, mantemos o nome gerado automaticamente.
    }
  }

  const responseSheetName = responseSheet ? responseSheet.getName() : "";
  const csvUrl = responseSheetName
    ? `https://docs.google.com/spreadsheets/d/${spreadsheet.getId()}/gviz/tq?tqx=out:csv&sheet=${encodeURIComponent(responseSheetName)}`
    : "";

  return {
    key: spec.key,
    title,
    form_id: form.getId(),
    form_url: form.getPublishedUrl(),
    edit_url: form.getEditUrl(),
    submit_url: `https://docs.google.com/forms/d/e/${form.getId()}/formResponse`,
    response_sheet: responseSheetName,
    csv_url: csvUrl,
    field_map: fieldMap,
  };
}

function addFormItem(form, field) {
  if (field.type === "number") {
    const item = form.addTextItem();
    item.setTitle(field.label);
    item.setRequired(field.required !== false);
    const validation = FormApp.createTextValidation()
      .requireNumber()
      .build();
    item.setValidation(validation);
    return item.getId();
  }

  if (field.type === "choice") {
    const item = form.addListItem();
    item.setTitle(field.label);
    item.setChoiceValues(field.options || []);
    item.setRequired(field.required !== false);
    return item.getId();
  }

  const item = form.addTextItem();
  item.setTitle(field.label);
  item.setRequired(field.required !== false);
  return item.getId();
}

function resolveResponseSheet(spreadsheet, beforeSheetIds) {
  const afterSheets = spreadsheet.getSheets();
  const created = afterSheets.find((sheet) => !beforeSheetIds.includes(sheet.getSheetId()));
  if (created) return created;
  const fallback = afterSheets.find((sheet) => String(sheet.getName()).toLowerCase().includes("form responses"));
  if (fallback) return fallback;
  return afterSheets.length ? afterSheets[afterSheets.length - 1] : null;
}

function writeConfigSheet(spreadsheet, output) {
  let sheet = spreadsheet.getSheetByName("CONFIG");
  if (!sheet) sheet = spreadsheet.insertSheet("CONFIG");
  sheet.clear();
  sheet.getRange(1, 1).setValue("Bundle de configuração do bolão (copie para o projeto)");
  sheet.getRange(2, 1).setValue(JSON.stringify(output, null, 2));
  sheet.getRange(2, 1).setWrap(true);
  sheet.setColumnWidth(1, 1200);
  sheet.setRowHeight(2, 1200);
}

function getFormSpecs() {
  return [
    {
      key: "PLAYOFF",
      title: "Bolão UEFA • Playoff",
      description: "Palpites de ida/volta e classificados do playoff.",
      fields: buildKnockoutFields("PO", 8),
    },
    {
      key: "ROUND_OF_16",
      title: "Bolão UEFA • Oitavas",
      description: "Palpites de ida/volta e classificados das oitavas.",
      fields: buildKnockoutFields("O8", 8),
    },
    {
      key: "QUARTER_FINALS",
      title: "Bolão UEFA • Quartas",
      description: "Palpites de ida/volta e classificados das quartas.",
      fields: buildKnockoutFields("Q", 4),
    },
    {
      key: "SEMI_FINALS",
      title: "Bolão UEFA • Semifinais",
      description: "Palpites de ida/volta e classificados das semifinais.",
      fields: buildKnockoutFields("S", 2),
    },
    {
      key: "FINAL",
      title: "Bolão UEFA • Final",
      description: "Palpite de placar da final e campeão.",
      fields: [
        { key: "F1_home", label: "Final - Gols time mandante", type: "number" },
        { key: "F1_away", label: "Final - Gols time visitante", type: "number" },
        { key: "F1_champion", label: "Campeão", type: "text" },
      ],
    },
    {
      key: "SPECIAL_PICKS",
      title: "Bolão UEFA • Picks Especiais",
      description: "Time favorito, artilheiro e garçom.",
      fields: [
        { key: "favorite_team", label: "Time favorito", type: "choice", options: TEAM_OPTIONS },
        { key: "top_scorer", label: "Artilheiro", type: "text" },
        { key: "top_assist", label: "Garçom", type: "text" },
      ],
    },
    {
      key: "LEAGUE_SUPERCLASSIC",
      title: "Bolão UEFA • Superclássicos da 1ª fase",
      description: "Palpites de placar dos 6 superclássicos da primeira fase.",
      fields: buildSuperclassicLeagueFields(),
    },
  ];
}

function buildKnockoutFields(prefix, ties) {
  const fields = [];
  for (let i = 1; i <= ties; i += 1) {
    fields.push(
      { key: `${prefix}${i}_ida_home`, label: `Confronto ${i} - Ida (casa)`, type: "number" },
      { key: `${prefix}${i}_ida_away`, label: `Confronto ${i} - Ida (visita)`, type: "number" },
      { key: `${prefix}${i}_volta_home`, label: `Confronto ${i} - Volta (casa)`, type: "number" },
      { key: `${prefix}${i}_volta_away`, label: `Confronto ${i} - Volta (visita)`, type: "number" },
      { key: `${prefix}${i}_classificado`, label: `Confronto ${i} - Classificado`, type: "text" }
    );
  }
  return fields;
}

function buildSuperclassicLeagueFields() {
  return [
    { key: "SC1_home", label: "SC1 Bayern de Munique x Chelsea (casa)", type: "number" },
    { key: "SC1_away", label: "SC1 Bayern de Munique x Chelsea (visita)", type: "number" },
    { key: "SC2_home", label: "SC2 Barcelona x Paris Saint-Germain (casa)", type: "number" },
    { key: "SC2_away", label: "SC2 Barcelona x Paris Saint-Germain (visita)", type: "number" },
    { key: "SC3_home", label: "SC3 Liverpool x Real Madrid (casa)", type: "number" },
    { key: "SC3_away", label: "SC3 Liverpool x Real Madrid (visita)", type: "number" },
    { key: "SC4_home", label: "SC4 Paris Saint-Germain x Bayern de Munique (casa)", type: "number" },
    { key: "SC4_away", label: "SC4 Paris Saint-Germain x Bayern de Munique (visita)", type: "number" },
    { key: "SC5_home", label: "SC5 Chelsea x Barcelona (casa)", type: "number" },
    { key: "SC5_away", label: "SC5 Chelsea x Barcelona (visita)", type: "number" },
    { key: "SC6_home", label: "SC6 Real Madrid x Manchester City (casa)", type: "number" },
    { key: "SC6_away", label: "SC6 Real Madrid x Manchester City (visita)", type: "number" },
  ];
}
