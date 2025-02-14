# **Mobile Banking Security Project**
# **Università Degli Studi di Bari Aldo Moro**
**Laurea Magistrale in Sicurezza Informatica**
**Corso: Sicurezza delle architetture orientate ai serivizi**

**Studente: Giacomo Pagliara**

**Docente: Prof. Giulio Mallardi**


Il progetto consiste in una web app per il Mobile Bnaking, finalizzata a gestire operazioni bancarie standard in maniera sicura ed interattiva. L'applicazione prevede l'accesso tramite OAuth 2.0 (con Microsoft e GitHub), mette a disposizione 
funzionalità di gestione del proprio conto corrente virtuale e implementa diverse misure di sicurezza per proteggere i dati degli utenti e garantire l'integrità del modello stesso di sistema di mobile bankng.

## Funzionalità

**Mobile Banking Security** implementa diverse funzionalità chiav. In particolare, la web app offre:

- **Autenticazione**:

    - **OAuth 2.0**: Gli utenti possono accedere tramite Microsoft o GitHub, sfruttando il flusso di autenticazione standard per ottenere l'accesso sicuro.


- **Dashboard Utente**:

    - **Visualizzazione del Saldo**: Gli utenti possono vedere il saldo attuale del proprio conto.

    - **Aggiunta di Fondi**: Gli utenti possono aggiungere fondi al proprio conto.
   
    - **Gestione delle Transazioni**:

        - **Creazione Transazioni**: Possibilità di effettuare transazioni inserendo importo, beneficiario, IBAN e descrizione.
        - **Verifica Transazioni**: Prima dell'esecuzione, il sistema effettua controlli sul saldo disponibile, sulla validità dell'IBAN e sui limiti (importo massimo per transazione, limite giornaliero e mensile).
        - **Storico Transazioni**: La dashboard mostra le ultime transazioni eseguite.

- **Token API e JWT**:

    - **Generazione Token**: Gli utenti autenticati possono generare token API basati su JWT, utilizzabili per accedere in modo sicuro alle API protette.
    - **Revoca e Verifica**: È possibile revocare i token e verificarne la validità.

- **2FA Autenticazione a due fattori per operazioni critiche**:

    - **Autenticazione a Due Fattori**: Per operazioni sensibili come il deposito, l'app richiede l'inserimento di un codice OTP.
    - **Setup del 2FA**: Se l'utente non ha ancora configurato il 2FA, viene generato un QR Code che può essere scansionato con un'app di autenticazione.

- **Conversione Valuta**:

    - **Tassi di Cambio in Tempo Reale**: L'app consulta i tassi di cambio correnti tramite [ExchangeRate-API](https://www.exchangerate-api.com/ "ExchangeRate-API").
    - **Utilizzo di un Convertitore**: Gli utenti possono convertire importi da EUR ad altre valute (USD, GBP, JPY, CHF, AUD) direttamente dalla dashboard.


## Architettura del Sistema
## Panoramica Architetturale
Il sistema di Mobile Banking Security è progettato seguendo un'architettura modulare e orientata ai servizi, con un focus specifico sulla sicurezza e la separazione delle responsabilità. L'architettura si compone di diversi layer interconnessi che garantiscono prestazioni, scalabilità e, soprattutto, un alto livello di protezione dei dati.


- **L'applicazione segue un'architettura REST suddivisa in**:

    - Frontend: HTML, CSS, JavaScript per la gestione dell'interfaccia utente.

    - Backend: Flask per la gestione delle API e della logica di business.

    - Database: Firestore (NoSQL) per la memorizzazione sicura delle informazioni.

- **Servizi di sicurezza**:
    - Autenticazione e Autorizzazione:
        - Integrazione OAuth 2.0 con provider multipli => Microsoft e GitHub
        - Sistema di Autenticazione a due fattori (2FA)
        - Gestione token JWT per le API
        - Gestione sicura delle sessioni utente
        - Security Headers configurati
    - Protezione dei Dati e dell'infrastruttura:
        - Crittografia AES per dati sensibili
        - HTTPS tramite *ngrok* per la comunicazione client-server
        - Protezione contro attacchi CSRF
        - Content Security Polict (CSP)
        - Security Headers configurati
    - Controllo Accessi
        - Rate Limiting sugli endpoint critici
        - Gestione delle sessioni
        - Validazione delle autorizzazioni per ogni endpoint
    - Sicurezza delle Transazioni
        - Validazione IBAN
        - Limiti per le transazioni
        - Verifica 2FA per operazioni critiche

- **Integrazioni API Esterne Exchange Rate API**
L'applicazione integra il servizio Exchange Rate API per fornire tassi di cambio in tempo reale. L'integrazione è implmentata attraverso due endpoint principali:
- Recupero Tassi di Cambio
- Conversione Valute
La valuta base è EUR.
Le valute supportate sono: USD,GBP,JPY,CHF,AUD.
L'aggiornamento automatico dei tassi avviene ogni 5 minuti.
![ExchangeRtaeAPI](static/images/ExchangeRate-API.png)

**Flusso di funzionamento**

1. Login OAuth2 → L'utente si autentica tramite Microsoft o GitHub.

2. Gestione della sessione → Dopo il login, viene generato un token JWT per proteggere le richieste successive.

3. Interazione con la dashboard → L'utente può consultare il saldo, effettuare transazioni e generare token API.

4. Sicurezza dei dati → Le richieste sono protette con CSRF, i dati sensibili sono crittografati e il rate limiting previene attacchi DoS.

5. Gestione transazioni → Il backend verifica la disponibilità del saldo e registra la transazione su Firestore.

### Utilizzo di ngrok per HTTPS

Nel contesto di questo progetto di Mobile Banking, l'utilizzo di HTTPS è fondamentale per garantire la sicurezza delle comunicazioni. Per questo scopo, è stato implementato ngrok, un tool che fornisce tunnel sicuri verso il server locale.

#### Cos'è ngrok
ngrok è uno strumento che crea un tunnel sicuro (HTTPS) verso il server di sviluppo locale, permettendo:
- Esposizione sicura dell'applicazione locale su Internet
- Generazione di un URL HTTPS pubblico
- Ispezione del traffico in tempo reale
- Testing dei webhook e delle integrazioni OAuth

#### Utilizzo nel Progetto
ngrok è stato fondamentale per:
1. **Autenticazione OAuth**:
   - Fornire URL di callback HTTPS validi per Microsoft e GitHub OAuth
   - Permettere ai provider di autenticazione di raggiungere l'applicazione in sviluppo

2. **Sicurezza delle Comunicazioni**:
   - Garantire che tutte le comunicazioni siano cifrate
   - Simulare un ambiente di produzione sicuro
   - Testare le funzionalità di sicurezza in un contesto HTTPS

3. **Testing delle Integrazioni**:
   - Verificare il corretto funzionamento delle callback OAuth
   - Testare le integrazioni con Exchange Rate API
   - Debugging delle richieste in tempo reale


## Autenticazione OAuth 2.0

L'applicazione implementa un sistema di autenticazione basato su OAuth 2.0, supportando due provider principali: Microsoft e GitHub. Questa scelta architetturale garantisce un processo di autenticazione sicuro e standardizzato.

### Provider OAuth

#### 1. Microsoft Authentication
- **Configurazione**:
  - Client ID e Secret gestiti tramite variabili d'ambiente
  - URI di reindirizzamento configurabile
  - Scope richiesti: `openid profile email user.read`

- **Flusso di Autenticazione**:
  1. L'utente clicca "Accedi con Microsoft"
  2. Viene generato uno state token crittograficamente sicuro
  3. Redirect all'endpoint di autorizzazione Microsoft
  4. Validazione risposta e token
  5. Recupero informazioni utente via Microsoft Graph API

- **Sicurezza**:
  - Validazione dello state token per prevenire CSRF
  - Rate limiting (5 tentativi al minuto)
  - Timeout di 15 minuti per il flusso di autenticazione
  - Rotazione delle sessioni dopo il login

#### 2. GitHub Authentication
- **Configurazione**:
  - Client ID e Secret specifici per GitHub
  - URI di reindirizzamento dedicato
  - Scope: `user:email` per accesso email verificata

- **Flusso di Autenticazione**:
  1. L'utente seleziona "Accedi con GitHub"
  2. Redirect all'endpoint di autorizzazione GitHub
  3. Scambio del codice di autorizzazione
  4. Recupero email verificata dell'utente
  5. Creazione o aggiornamento profilo utente

- **Sicurezza**:
  - Verifica email primaria verificata
  - Rate limiting sulle richieste
  - Validazione token di accesso
  - Protezione CSRF integrata

### Gestione Post-Autenticazione

Dopo l'autenticazione riuscita con uno dei provider:
1. Viene creato un documento utente in Firestore (se nuovo utente)
2. Viene generato un secret per 2FA (se non presente)
3. Viene inizializzata una sessione sicura con:
   - Timeout configurabile
   - Cookie httpOnly
   - Flags di sicurezza appropriate
4. L'utente viene reindirizzato alla dashboard


## Bibliografia
- [SOA](https://aws.amazon.com/it/what-is/service-oriented-architecture/#:~:text=L'architettura%20orientata%20ai%20servizi%20(SOA)%20%C3%A8%20un%20metodo,attraverso%20piattaforme%20e%20lingue%20diverse.)

