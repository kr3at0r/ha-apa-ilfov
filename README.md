# Apă Ilfov pentru Home Assistant

Citește facturile Apa-Canal Ilfov primite pe e-mail (PDF atașat) și creează senzori: ultima factură (lei, cu istoricul în atributul `facturi`), scadență, index apometru, consum apă și canal, total ultimele 12 luni, număr de facturi și „factură de verificat”.

La fiecare factură nouă emite evenimentul `apa_ilfov_factura_noua`.

## Instalare prin HACS
1. HACS → ⋮ → Depozite personalizate → URL-ul acestui repo, categoria „Integration”.
2. Descarcă „Apă Ilfov” și repornește Home Assistant.
3. Setări → Dispozitive și servicii → Adaugă integrare → „Apă Ilfov”.
4. Introdu adresa de e-mail și o parolă de aplicație (pentru Gmail). Serverul IMAP și expeditorul sunt completate implicit.

La prima rulare citește tot istoricul, fără notificări. Mesajele nu sunt marcate ca citite. Facturile fără linie de canal (apometru vechi) sunt ignorate; se poate schimba din Opțiuni.
