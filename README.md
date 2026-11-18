> Per la distribuzione HTTPS consultare [deploy/PRODUZIONE.md](deploy/PRODUZIONE.md).

# CP Fitness

Gestionale web multitenant per palestre: React/Vite e API FastAPI con SQLite. Include anagrafiche, tipologie e abbonamenti, storico degli incassi, ingressi/uscite, scadenze, operatori e creazione delle palestre da parte del super amministratore.

## Avvio locale (PowerShell)

In un primo terminale, dalla cartella del progetto:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt
$env:SUPERADMIN_EMAIL = "admin@example.it"
$env:SUPERADMIN_PASSWORD = "ScegliUnaPasswordSicura"
python -m uvicorn backend.main:app --reload --port 8000
```

Le variabili creano il super amministratore solo al primo avvio, se non ne esiste già uno. Conservare le credenziali in modo sicuro. Il database viene creato in `backend/fitness.db`; `DATABASE_PATH` permette di scegliere un altro percorso. La documentazione API è disponibile su `http://localhost:8000/docs`.

In un secondo terminale:

```powershell
cd frontend
npm install
npm run dev
```

Aprire `http://localhost:5173`, accedere come super amministratore e creare una palestra con il suo amministratore. Uscire e accedere con il nuovo account per creare operatori, clienti, tipologie e abbonamenti. Le email di accesso devono essere univoche nell'intera installazione.

Per configurare origini e indirizzo API usare rispettivamente `CORS_ORIGINS` nel backend (elenco separato da virgole) e `VITE_API_URL` nel frontend. Le sessioni scadono dopo 12 ore. Gli ingressi richiedono un abbonamento attivo e non consentono un doppio ingresso aperto; un certificato scaduto viene segnalato nel registro.

## Limiti attuali

Questa è una base operativa, non una replica completa del gestionale negli screenshot: corsi e prenotazioni, documenti e allegati, messaggi email/SMS, contabilità dettagliata, magazzino, federazioni e integrazione con lettori fisici non sono ancora implementati. Gli incassi registrati da questa versione hanno uno storico con data, operatore, metodo e nota; gli importi registrati nelle versioni precedenti rimangono nel totale ma non possono essere ricostruiti nello storico. Non ? presente una prima nota contabile. Prima di un utilizzo reale servono, tra l'altro, distribuzione HTTPS, backup e ripristino verificati, gestione password e account, audit, protezione dagli attacchi al login e una revisione di sicurezza e privacy; SQLite è pensato per l'avvio locale, non per una distribuzione multiistanza.
