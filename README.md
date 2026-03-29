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
- Os placares ao vivo estão simulados localmente para demonstrar atualização automática sem depender de API externa.
- A integração futura pode substituir a função de live timeline por um provedor real de dados esportivos.

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

## Atualização automática de placares (API-Football)

O projeto agora possui um workflow dedicado para placares ao vivo:

- arquivo: `.github/workflows/live-scores-sync.yml`
- frequência: a cada 10 minutos
- saída atualizada automaticamente: `api/matches.json` e `api/matches.js`

### Configuração no GitHub (uma vez)

No repositório, abra `Settings > Secrets and variables > Actions` e crie:

1. Secret obrigatório:
- `API_FOOTBALL_KEY` = sua chave da API-Football

2. Variável recomendada:
- `UCL_API_SEASON` = `2025` para a edição Champions 2025/26

3. Variáveis opcionais (se quiser sobrescrever padrão):
- `API_FOOTBALL_HOST` (padrão: `v3.football.api-sports.io`)
- `API_FOOTBALL_BASE_URL` (padrão: `https://v3.football.api-sports.io`)
- `API_FOOTBALL_LEAGUE_ID` (padrão: `2`)

### Primeiro disparo manual

1. Abra `Actions` no GitHub.
2. Selecione `Live Scores Sync (API-Football)`.
3. Clique em `Run workflow`.

Depois disso, o job agendado mantém os placares atualizados automaticamente.
