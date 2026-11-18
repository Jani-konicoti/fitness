# Distribuzione di CP Fitness

Questa configurazione predisposta per un server Linux con Docker Engine e Docker Compose pubblica `https://fitness.centropaghe.it` tramite Caddy. Non pubblica la porta 8000 del backend né usa il server di sviluppo Vite.

## Rete e certificato

- Il record DNS A/AAAA del dominio deve puntare al server (rimuovere AAAA se IPv6 non è configurato).
- Aprire in ingresso TCP 80 e 443 verso il container Caddy. La porta 80 serve per il reindirizzamento e la verifica ACME HTTP; Caddy ottiene e rinnova automaticamente il certificato. La porta TCP 443 serve HTTPS. Non occorre esporre 5173 o 8000.
- Se è già presente un reverse proxy o le porte sono occupate, il sistemista deve adattare la configurazione: questa installazione presume che Caddy gestisca direttamente 80/443 e TLS. Non avviare una seconda istanza sulla stessa porta.
- La subnet Docker `172.30.0.0/24` deve essere libera; se va cambiata, aggiornare contemporaneamente gli IP statici in `compose.yaml` e l'IP proxy attendibile in `Dockerfile.backend`.

## Preparazione e avvio

1. Copiare i sorgenti sul server. Creare `.env` da `.env.production.example`, impostare il dominio, un indirizzo email valido per ACME e le credenziali iniziali. Proteggere `.env` con permessi stretti (`chmod 600 .env`); non inserirlo in Git. Scegliere una password lunga e casuale.
2. Eseguire `docker compose config --quiet`, quindi `docker compose up -d --build`.
3. Verificare `docker compose ps`, `docker compose logs web backend`, il certificato e l'accesso a `https://fitness.centropaghe.it`. Le richieste `/api` usano la stessa origine HTTPS. Provare login, accesso a un tenant e caricamento/apertura di un allegato di prova.
4. Le variabili `SUPERADMIN_EMAIL` e `SUPERADMIN_PASSWORD` creano il super amministratore solo se non ne esiste già uno. Cambiarle successivamente non modifica l'account esistente. Per un'installazione nuova non utilizzare la password di sviluppo né importare automaticamente i dati dimostrativi.

## Dati, aggiornamenti e backup

Il volume `fitness_data` contiene SQLite **e gli allegati dei clienti**; `caddy_data` contiene certificati e chiavi. Conservare entrambi. Non eseguire `docker compose down -v`: elimina i volumi. Su ogni aggiornamento effettuare prima un backup verificato, poi ricostruire con `docker compose up -d --build`.

Per un backup coerente di SQLite con il servizio attivo, su host Linux:

```sh
mkdir -p backups
chmod 700 backups
docker compose exec -T backend python -c "import sqlite3; src=sqlite3.connect('/data/fitness.db'); dst=sqlite3.connect('/data/backup.db'); src.backup(dst); dst.close(); src.close()"
docker compose cp backend:/data/backup.db ./backups/fitness.db
docker compose exec -T backend python -c "import os; os.remove('/data/backup.db')"
chmod 600 backups/fitness.db
```

Cifrare e conservare i backup fuori dal server, definirne la frequenza e provarne regolarmente il ripristino. Per ripristinare, fermare l'applicazione e copiare il database verificato nel volume conservando proprietario UID 10001 e permessi, quindi riavviare. Effettuare la prova prima in un ambiente isolato. Per migrare dati esistenti serve una copia coerente del database e una procedura separata: il file locale di sviluppo non viene incluso nelle immagini Docker.

## Limiti prima dell'uso reale

La configurazione HTTPS non equivale a una certificazione di sicurezza. Il progetto gestisce dati personali e certificati medici; richiede prima del rilascio una revisione di sicurezza e privacy, protezioni contro tentativi ripetuti di login, gestione credenziali e recupero account, audit e un piano di backup/ripristino verificato. Le sessioni sono in localStorage. SQLite è configurato per un solo backend e un solo host, non per più repliche o storage di rete condiviso. Le immagini usano tag di versione e i requisiti Python hanno intervalli: per una distribuzione riproducibile bloccare versioni e digest nel processo di rilascio.
