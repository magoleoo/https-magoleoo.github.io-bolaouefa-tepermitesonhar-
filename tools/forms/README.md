# Forms do Bolão (Google Forms)

Este diretório contém um script para criar o pacote de Forms da temporada.

## Arquivo principal

- `create_bolao_forms.gs`: script de Google Apps Script que cria:
  - Form de Playoff
  - Form de Oitavas
  - Form de Quartas
  - Form de Semifinais
  - Form de Final
  - Form de Picks Especiais (favorito/artilheiro/garçom)
  - Form de Superclássicos da 1ª fase

## Como executar

1. Abra [script.new](https://script.new).
2. Crie um projeto e cole o conteúdo de `create_bolao_forms.gs`.
3. Ajuste `SEASON_LABEL` e `PARTICIPANTS`.
4. Execute `createBolaoFormsBundle()`.
5. Copie o JSON gerado no `Logger` ou na aba `CONFIG` da planilha criada.

## Resultado esperado

O script gera:

- 1 planilha de respostas da temporada
- 7 Forms vinculados nessa planilha
- `field_map` de cada Form (com `entry.<id>`) para integração com o app
- URLs prontas:
  - `form_url`
  - `submit_url`
  - `csv_url`

## Integração no frontend

Hoje o app já usa integração ativa para Quartas via `window.quarterFinalsFormsConfig` em `data.js`.

Para ativar:

1. `csvUrl` = `forms.QUARTER_FINALS.csv_url`
2. `submitUrl` = `forms.QUARTER_FINALS.submit_url`
3. `fieldMap` = `forms.QUARTER_FINALS.field_map`

Depois disso, os envios de quartas podem ser enviados direto pelo app e lidos via CSV.
