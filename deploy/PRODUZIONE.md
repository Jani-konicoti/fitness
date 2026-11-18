# Distribuzione di CP Fitness

Questa configurazione usa il reverse proxy nginx esterno per HTTPS e il certificato. Nginx inoltra a `http://192.168.7.200:8000`, dove Caddy serve il frontend e inoltra `/api` al backend sulla rete Docker. Il backend non è direttamente esposto.

## Rete e certificato

- Il DNS pubblico e le porte TCP 80 e 443 sono gestiti dal reverse proxy nginx, che gestisce anche il certificato e il rinnovo.
- Il server fitness deve essere raggiungibile dal reverse proxy su `192.168.7.200:8000`. Limitare l'accesso a tale porta alla rete e al proxy autorizzati: il collegamento interno è HTTP e non è cifrato. L'indirizzo è vincolato in `compose.yaml` e va aggiornato se cambia l'IP del server.
- La subnet Docker `172.30.0.0/24` deve essere libera; se va cambiata, aggiornare contemporaneamente gli IP statici in `compose.yaml` e l'IP proxy attendibile in `Dockerfile.backend`.

## Preparazione e avvio

1. Copiare i sorgenti sul server. Creare `.env` da `.env.production.example`, impostare il dominio e le credenziali iniziali. Proteggere `.env` con permessi stretti (`chmod 600 .env`); non inserirlo in Git. Scegliere una password lunga e casuale. Il certificato è gestito esternamente e `ACME_EMAIL` non viene usata da questa configurazione.
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
