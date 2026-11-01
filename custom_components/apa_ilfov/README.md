# Apă Ilfov (Home Assistant)

Citește facturile Apa-Canal Ilfov primite pe e-mail (PDF atașat) și creează senzori:
ultima factură (lei, cu istoricul în atribut `facturi`), scadență, index apometru, consum apă / canal,
total ultimele 12 luni, număr facturi, „factură de verificat”.

Eveniment la factură nouă: `apa_ilfov_factura_noua`.

Instalare: copiază folderul `apa_ilfov` în `/config/custom_components/`, repornește HA,
Setări → Dispozitive și servicii → Adaugă integrare → „Apă Ilfov”.
La prima rulare citește tot istoricul, fără notificări.
Facturile fără linie de canal (apometru vechi) sunt ignorate (se poate schimba din Opțiuni).
