**Autentificare prin ROeID, Google sau eIDAS**

Conturile eToll create prin ROeID, Google sau eIDAS nu au o parolă eToll, așa că nu se puteau conecta în integrare ([#13](https://github.com/cnecrea/tollro/issues/13)). Acum, la adăugarea integrării, alegi cum te autentifici:

- **Cu e-mail (sau telefon) și parolă** — ca până acum.
- **Prin pagina oficială eToll** — se deschide pagina de autentificare eToll, unde apeși „Continuă cu ROeID” (sau Google / eIDAS) și te autentifici ca în aplicația TollRo. Home Assistant primește doar accesul la cont, nu și datele tale de autentificare.

**Alte schimbări**
- Din **Reconfigurare** poți schimba metoda de autentificare (de exemplu, de pe parolă pe ROeID), fără să ștergi integrarea; vehiculele, entitățile și istoricul rămân.
- Un cont conectat prin pagina eToll se reconectează, la nevoie, tot prin pagina eToll.
- Când autentificarea cu parolă eșuează, mesajul amintește și de varianta pentru conturile ROeID, Google sau eIDAS.

**Actualizare**
Instalările existente funcționează mai departe, fără reconfigurare. Necesită în continuare Home Assistant 2025.11 sau mai nou.

La prima folosire a autentificării prin pagina eToll, pagina My Home Assistant îți poate cere adresa instanței tale Home Assistant — prin ea revine browserul în Home Assistant după autentificare.
