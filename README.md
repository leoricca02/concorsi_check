# Concorsi Check

Controlla da solo, il martedì e il venerdì (quando esce la Gazzetta Ufficiale), i siti dei concorsi
pubblici italiani e ti avvisa solo per quelli adatti al tuo profilo: laurea magistrale in
Engineering in Computer Science (LM-32), laurea triennale in Ingegneria Informatica (L-8),
interesse per software, dati, AI e cybersecurity.

**Costo: zero.** Gira su GitHub Actions (gratis per i repository pubblici; per quelli privati ci
sono 2.000 minuti al mese gratuiti e un controllo ne usa 2-3). Non servono server né API a pagamento.

## Come funziona

```
GitHub Actions (ogni lunedì)
   │
   ├─ inPA (API pubblica)            ~1.700 procedure aperte, lette tutte
   ├─ Gazzetta Ufficiale 4ª serie    ultimi fascicoli del martedì e venerdì
   └─ pagine "Concorsi" degli enti   Banca d'Italia, CONSOB, IVASS, ACN, AgID, Istat, ...
   │
   ▼
valutazione con le regole di config.yaml  →  punteggio + motivi
   │
   ▼
solo i bandi NUOVI e rilevanti  →  report in reports/ultimo.md
                                    + issue su GitHub (arriva per email)
                                    + email e/o Telegram (facoltativi)
```

- **inPA** è la fonte principale: dal 2023 le amministrazioni pubbliche devono pubblicare lì i
  bandi (anche Banca d'Italia, CONSOB, ACN, Istat li pubblicano su inPA). Per i bandi promettenti
  il programma scarica anche il dettaglio con i requisiti (es. "LM-32").
- **Gazzetta Ufficiale** copre enti che non usano inPA (università, sanità, alcuni enti locali).
- Le **pagine degli enti** sono una rete di sicurezza: il programma memorizza i link presenti e
  ti segnala quelli nuovi. Al primo avvio i link già presenti vengono solo memorizzati (sono spesso
  concorsi vecchi), tranne per le fonti con `segnala_al_primo_run: true`.
- Lo stato (quali bandi hai già visto) è in `data/stato.json`: ogni bando viene segnalato una sola volta.
  Nel report trovi anche l'elenco dei bandi segnalati in passato e non ancora scaduti.
- Se una fonte non risponde o cambia struttura, il report lo dice nella sezione "⚠️ Fonti con problemi".

### Come si decide se un bando è interessante

In `config.yaml`, sezione `profilo`. Ogni regola ha un peso; il bando è segnalato se il totale
arriva alla `soglia` (5) e se corrisponde ad almeno una regola "di materia"
(`richiesta_una_di`: profilo informatico, laurea informatica richiesta, dati/AI, cybersecurity,
qualsiasi laurea). Esempi di pesi:

| Regola | Peso |
|---|---|
| titolo/profilo informatico, ICT, software, sistemi informativi | +6 |
| requisiti con LM-32, LM-18, LM-66, L-8, L-31, ingegneria informatica | +5 |
| data science / AI, cybersecurity | +5 |
| laurea magistrale / elevate professionalità / esperti | +3 |
| laurea triennale / area dei funzionari | +2 |
| Roma, Lazio o sede nazionale; tempo indeterminato | +1 |
| area istruttori/operatori, CTER, assistenti (di solito serve solo il diploma) | −6 |
| dirigenza (serve esperienza) | −3 |
| mobilità, stabilizzazioni, profili sanitari/scolastici | escluso |

Frasi standard come *"conoscenza delle applicazioni informatiche più diffuse"* (presente in quasi
tutti i bandi) vengono ignorate, altrimenti ogni concorso sembrerebbe da informatico.
Le stelle nel report: ⭐⭐⭐ punteggio ≥ 12, ⭐⭐ ≥ 8, ⭐ il resto.

## Attivazione (10 minuti)

1. **Scegli la frequenza** in `.github/workflows/controllo-concorsi.yml` (settimanale di default;
   ci sono le righe pronte per "ogni due settimane" e "ogni mese"). Se controlli una volta al mese,
   in `config.yaml` metti `fascicoli: 9` per la Gazzetta.
2. **Primo controllo**: parte da solo a ogni modifica di `config.yaml`; oppure scheda *Actions* →
   *Controllo concorsi* (nella colonna a sinistra, non "Test") → *Run workflow*. Al termine trovi
   il report in `reports/ultimo.md` e, se ci sono novità, una nuova issue.
3. **Notifiche** (facoltative, in *Settings → Secrets and variables → Actions → New repository secret*):
   - **Issue GitHub**: già attive. GitHub ti manda un'email per ogni nuova issue se "guardi" il
     repository (pulsante *Watch* → *All activity*, oppure almeno *Issues*).
   - **Email (Gmail)**: `EMAIL_USER` = il tuo indirizzo Gmail, `EMAIL_PASSWORD` = una
     [password per le app](https://myaccount.google.com/apppasswords) (serve la verifica in due
     passaggi), `EMAIL_TO` = destinatario (facoltativo, di default te stesso).
   - **Telegram** (notifica sul telefono): crea un bot con [@BotFather](https://t.me/BotFather) →
     `TELEGRAM_BOT_TOKEN`; scrivi un messaggio al bot e prendi il tuo id da
     `https://api.telegram.org/bot<TOKEN>/getUpdates` → `TELEGRAM_CHAT_ID`.

> Nota: le esecuzioni programmate partono solo dal branch predefinito del repository.

## Verifica AI (facoltativa)

Per i soli bandi già filtrati, un modello AI legge il bando completo (anche il PDF allegato su inPA)
e dice se puoi partecipare: ✅ adatto, ❔ da verificare, ❌ non adatto (questi finiscono in una
sezione chiusa del report, così puoi controllarli). Nel report compaiono laurea e classi ammesse.

- **Gratis (Gemini)**: crea una chiave su [Google AI Studio](https://aistudio.google.com/apikey) e
  aggiungila come secret `GEMINI_API_KEY`.
- **Claude (a pagamento)**: in `config.yaml` metti `provider: anthropic` e `modello: claude-opus-5`,
  poi il secret `ANTHROPIC_API_KEY`. Circa 5-8 centesimi a bando (1-2 con `claude-haiku-4-5`).

Senza chiave la verifica viene saltata. Il profilo del candidato è in `config.yaml` → `ai.candidato`.

## Pagina web e 👍/👎

`docs/index.html` (pubblicata con GitHub Pages) mostra i bandi aperti con scadenza, esito AI e i
pulsanti 👍 / 👎 / ✉️ "mi sono candidato". I voti finiscono in `data/preferenze.json`:
- 👎 nasconde il bando per sempre (report, scadenze, pagina);
- dopo 5 voti (almeno uno 👍 e uno 👎) si attiva il **punteggio personale**: un classificatore
  Naive Bayes sulle parole di titolo, ente e profilo aggiunge da −4 a +4 punti ai bandi simili a
  quelli votati ("simile a bandi che ti sono piaciuti");
- gli ultimi bandi votati vengono dati all'AI come esempi dei tuoi gusti.

Attivazione: *Settings → Pages → Deploy from a branch →* branch principale, cartella `/docs`.
Per votare serve un token GitHub *fine-grained* limitato a questo repository con permesso
*Contents: Read and write*, da incollare una volta nella pagina (⚙︎): resta solo nel tuo browser.

Il profilo del candidato per l'AI sta nel secret `PROFILO_CANDIDATO` (il repository è pubblico).

## Aggiungere o togliere siti

In `config.yaml`, sezione `fonti`. Per un nuovo ente basta l'URL della sua pagina "Concorsi" /
"Lavora con noi" / "Bandi di concorso":

```yaml
  inail:
    tipo: pagina
    ente: INAIL
    url: https://www.inail.it/...pagina-concorsi...
    # selettore: "main"         # facoltativo: guarda solo i link dentro questo elemento CSS
    # segnala_al_primo_run: true
```

Per disattivare una fonte: `attiva: false`.

## Uso in locale

```bash
python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m concorsi --prova --no-notifiche   # non salva lo stato e non invia nulla
.venv/bin/pytest                                     # test (senza rete, con pagine di esempio)
```

## Struttura

```
config.yaml                      profilo, fonti, notifiche
concorsi/fonti/inpa.py           API inPA
concorsi/fonti/gazzetta.py       Gazzetta Ufficiale, 4ª serie speciale
concorsi/fonti/pagina.py         qualunque pagina web con l'elenco dei bandi
concorsi/valutazione.py          punteggio di rilevanza
concorsi/stato.py                memoria dei bandi già visti (data/stato.json)
concorsi/report.py               report Markdown / email / Telegram
concorsi/main.py                 esecuzione completa
.github/workflows/               controllo programmato e test
```
