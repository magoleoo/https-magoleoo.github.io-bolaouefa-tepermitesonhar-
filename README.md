# Bolão Champions League

MVP estático para um site privado de bolão da Champions League com:

- login simples por participante
- ranking recalculado no navegador
- formulário de palpites dos jogos
- palpites especiais de favorito, campeão, artilheiro e garçom
- suporte às regras de pontuação por fase, bônus e casos especiais
- camada preparada para atualização automática de placares

## Como rodar

Na pasta do projeto:

```bash
cd /Users/leopicca/Downloads/06_Projetos_e_Criacao/champions-bolao
python3 -m http.server 4173
```

Depois abra no navegador:

[http://localhost:4173](http://localhost:4173)

## Códigos de teste

- `Leo Picca` -> `UCL-101`
- `Felippe Leite` -> `UCL-116`
- `Victor` -> `UCL-114`

## Observações importantes

- Este MVP usa autenticação local no navegador. Para produção, o ideal é trocar por backend com sessões reais.
- O app usa fallback local de resultados quando a API está indisponível, para evitar tela vazia.
- A sincronização via API-Football está com validação fail-fast para bloquear escrita de `matches` vazio.

## Próximo passo técnico

Agora o projeto também tem uma base de backend em [backend/README.md](/Users/leopicca/Downloads/06_Projetos_e_Criacao/champions-bolao/backend/README.md) com:

- schema inicial de banco
- rotas HTTP para ranking, jogos, sync e recálculo
- sincronização preparada para API-Football
- motor de pontuação isolado do frontend

## Forms para operação recorrente

Para rodar o bolão temporada após temporada com Google Forms:

- fluxo técnico: [docs/forms-flow.md](/Users/leopicca/Downloads/06_Projetos_e_Criacao/champions-bolao/docs/forms-flow.md)
- script de criação dos Forms: [tools/forms/create_bolao_forms.gs](/Users/leopicca/Downloads/06_Projetos_e_Criacao/champions-bolao/tools/forms/create_bolao_forms.gs)
- guia rápido: [tools/forms/README.md](/Users/leopicca/Downloads/06_Projetos_e_Criacao/champions-bolao/tools/forms/README.md)

## Atualização de placares via API (multi-provider)

O projeto possui um workflow dedicado para sincronizar placares:

- arquivo: `.github/workflows/live-scores-sync.yml`
- disparo manual (`workflow_dispatch`) e agendado (a cada 20 min)
- observação: só executa de fato quando `ENABLE_API_SYNC=true`
- saída atualizada: `api/matches.json` e `api/matches.js`

### Configuração no GitHub (uma vez)

No repositório, abra `Settings > Secrets and variables > Actions`.

1. Variáveis obrigatórias:
- `ENABLE_API_SYNC` = `true`
- `LIVE_SCORES_PROVIDER` = `api_football` ou `football_data`
- `UCL_API_SEASON` = `2025` (Champions 2025/26)

2. Se usar `api_football`:
- Secret: `API_FOOTBALL_KEY`
- Variáveis opcionais:
- `API_FOOTBALL_HOST` (padrão: `v3.football.api-sports.io`)
- `API_FOOTBALL_BASE_URL` (padrão: `https://v3.football.api-sports.io`)
- `API_FOOTBALL_LEAGUE_ID` (padrão: `2`)

3. Se usar `football_data`:
- Secret: `FOOTBALL_DATA_API_KEY` (ou reaproveite `API_FOOTBALL_KEY`)
- Variáveis opcionais:
- `FOOTBALL_DATA_BASE_URL` (padrão: `https://api.football-data.org/v4`)
- `FOOTBALL_DATA_COMPETITION_CODE` (padrão: `CL`)

4. Validação de segurança:
- `API_FOOTBALL_REQUIRE_NON_EMPTY` = `true` (recomendado para bloquear sync vazio)

### Primeiro disparo manual

1. Abra `Actions` no GitHub.
2. Selecione `Live Scores Sync (API Providers)`.
3. Clique em `Run workflow`.
