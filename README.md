# ORCID → BibTeX → BibBase

Pipeline che rigenera ogni settimana `publications.bib` dal record ORCID pubblico
e lo espone a un URL stabile da usare come sorgente in BibBase.

## Setup (una volta sola)

1. Crea un repo GitHub **pubblico** (es. `publications`) e copia dentro questi file.
2. In *Settings → Secrets and variables → Actions → Variables* aggiungi:
   - `ORCID_ID` = il tuo iD (es. `0000-0002-1825-0097`)
   - `CROSSREF_MAILTO` = la tua email (opzionale, per il polite pool di Crossref)
3. Tab *Actions* → "Update publications.bib from ORCID" → *Run workflow*.
   Il primo run produce `publications.bib` e `cache.json` e li committa.
4. L'URL stabile del file è
   `https://raw.githubusercontent.com/<utente>/<repo>/main/publications.bib`
   (se preferisci GitHub Pages: *Settings → Pages → Deploy from branch main /root*,
   poi `https://<utente>.github.io/<repo>/publications.bib`).
5. Su BibBase crea/aggiorna la sorgente puntando a quell'URL, oppure usa direttamente
   l'embed:
   ```html
   <script src="https://bibbase.org/show?bib=https://raw.githubusercontent.com/<utente>/<repo>/main/publications.bib&jsonp=1"></script>
   ```

## Come funziona

- Per ogni work ORCID con DOI il BibTeX arriva da Crossref (qualità alta, campi completi).
- Senza DOI si usa la citation BibTeX salvata su ORCID; altrimenti un `@misc` minimale.
- Le chiavi BibTeX vengono normalizzate dal DOI (es. `10_1145_1234567`) così restano stabili tra i run.
- `cache.json` evita di richiamare Crossref per i lavori già risolti: per forzare un refresh
  completo cancellalo e rilancia il workflow.

## Test locale

```bash
pip install requests
ORCID_ID=0000-0002-1825-0097 python scripts/orcid_to_bib.py
```
