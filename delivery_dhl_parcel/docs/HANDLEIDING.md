# DHL Parcel Delivery Carrier — Handleiding

Deze handleiding beschrijft hoe je de module **DHL Parcel Delivery Carrier**
installeert, configureert en gebruikt in de dagelijkse Odoo-workflow.

> **Versie van de module:** 17.0.0.4.0
> **Voor Odoo:** 17.0 (community en enterprise)

---

## Inhoud

1. [Inleiding](#1-inleiding)
2. [Quick Start](#2-quick-start)
3. [Concepten](#3-concepten)
4. [Wat heb je nodig aan DHL-zijde?](#4-wat-heb-je-nodig-aan-dhl-zijde)
5. [Installatie](#5-installatie)
6. [Verzendmethodes aanmaken](#6-verzendmethodes-aanmaken)
7. [Prijszetting](#7-prijszetting)
8. [Dagelijkse workflow](#8-dagelijkse-workflow)
9. [Multicollo (meerdere pakketten in één zending)](#9-multicollo-meerdere-pakketten-in-één-zending)
10. [Put in Pack — uitgelegd](#10-put-in-pack--uitgelegd)
11. [Het label en de tracking](#11-het-label-en-de-tracking)
12. [Annuleren](#12-annuleren)
13. [Wat als het misgaat](#13-wat-als-het-misgaat)
14. [Talen](#14-talen)
15. [Korte FAQ](#15-korte-faq)

---

## 1. Inleiding

Deze module verbindt Odoo met **DHL Parcel (Benelux)** via de API
`api-gw.dhlparcel.nl`. Wanneer je een delivery (`stock.picking`) valideert in
Odoo, maakt de module automatisch een verzending aan bij DHL, haalt het
verzendlabel op als PDF, hangt dat aan de delivery, en bewaart de
tracking-codes op de picking.

De module ondersteunt:

- **Outbound vanuit BE, NL en LU** naar 31 Europese bestemmingen.
- **Retours** vanuit dezelfde 31 landen terug naar je Benelux-magazijn.
- **Multicollo**: één order = één DHL-shipment met N pakketten (één
  multipage PDF en N trackers).
- **Mixed shipments**: verschillende parceltypes binnen één zending.
- **Drie prijsmodellen**: vaste prijs, gewichtstaffel, of per-type tarief.

De module doet niet:

- **Live tarieven** ophalen — de DHL Parcel-gateway heeft geen rate-endpoint.
  Prijzen stel je in op de carrier zelf.
- **Verzendingen annuleren via de API** — DHL's publieke API biedt geen
  cancel-endpoint. Annuleren gebeurt in het My DHL Parcel-portaal (zie
  hoofdstuk 12).
- **Verzenden vanuit landen buiten BE/NL/LU** — daarvoor heb je een ander
  DHL-contract en een andere module nodig.

---

## 2. Quick Start

Voor wie meteen aan de slag wil. Vijf stappen van nul naar je eerste label:

1. **Installeer** de module via Apps → zoek *DHL Parcel Delivery Carrier* →
   Install.
2. Ga naar **Inventory → Configuration → Shipping Methods → New**.
3. Provider = **DHL Parcel (Benelux)**. Een tab "DHL Parcel" verschijnt.
4. Op die tab: vul **User ID**, **API Key**, **Account ID** in (zie sectie
   4 voor waar je die haalt). Kies een **Parcel type** (bv. *Pakket tot
   10kg*) en zet een **Flat price**. Selecteer **Countries** (de lijst is
   automatisch beperkt tot de 31 ondersteunde landen).
5. Op je eerste echte order: klik **Add Shipping**, kies deze methode,
   confirm het order, ga naar de gegenereerde delivery, **Validate** — DHL
   maakt het label en je vindt de PDF als bijlage op de delivery. Klaar.

Voor de volledige uitleg en geavanceerd gebruik: lees verder.

---

## 3. Concepten

Drie ideeën die de module duidelijker maken:

### Eén verzendmethode per parceltype

DHL heeft zes parceltypes (Envelop, Brievenbuspakket, Pakket tot 10kg, tot
20kg, tot 31kg, Pallet tot 1000kg). De module volgt het Odoo-patroon van
*"één shipping method per duidelijk product"*: voor elk parceltype dat je
wil aanbieden maak je een aparte verzendmethode aan. De keuze van type
gebeurt dus bij het kiezen van de verzendmethode, niet later in de flow.

Voor het uitzonderlijke geval waar je verschillende parceltypes in **één
zending** wil combineren is er de speciale optie **Gemengd** (MIX), zie
secties 6 en 9.

### Multicollo

Eén Odoo-delivery wordt altijd één DHL-shipment, ook als die zending uit
meerdere pakketten bestaat. DHL geeft dan één tracker per pakket en
**één multipage PDF** met alle labels. Dat is wat "multicollo" betekent.

Het aantal pakketten kan op twee manieren bepaald worden — zie sectie 9.

### Prijzen worden lokaal berekend

DHL's API geeft geen prijzen terug. De prijs die op het order verschijnt
komt uit de configuratie van de carrier: vaste prijs, gewichtstaffel, of
(bij MIX) een tabel met tarieven per parceltype.

---

## 4. Wat heb je nodig aan DHL-zijde?

### Een DHL eCommerce Benelux-account

Het soort contract dat je nodig hebt heet **DHL Parcel Benelux** of **DHL
eCommerce Benelux** (twee namen voor hetzelfde product). Andere DHL-takken
(DHL Express, DHL Parcel DE, ...) werken niet met deze module.

### API-credentials

Hiervoor zijn twee stappen nodig: **eerst** moet DHL API-toegang activeren
op je account, **daarna** kan je zelf credentials aanmaken in het portaal.

#### Stap 1 — DHL moet de API-rol toekennen op je account

API-toegang is geen standaardonderdeel van een DHL eCommerce Benelux-
account. Voor je überhaupt een API Key kan aanmaken in het portaal, moet
je DHL-contactpersoon (of DHL eCommerce support) de **API-rol** toekennen
op je account. Dit gebeurt manueel aan DHL-zijde — je kan het zelf niet
forceren.

Hoe je dat vraagt:

- Mail je DHL-account-manager of DHL eCommerce-support.
- Vermeld je DHL-klantnummer (zelfde nummer dat later je Account ID wordt).
- Vraag expliciet om "API access" / "de API-rol" op je account te
  activeren zodat je API keys kan aanmaken via het portaal.

Tot DHL bevestigt dat de rol toegekend is, ga je in het portaal alleen
een "Connections"-pagina zien — geen API Keys-sectie. Dat is het signaal
dat stap 1 nog niet rond is.

#### Stap 2 — API Key aanmaken in het My DHL Parcel-portaal

Eens DHL de rol heeft toegekend: log in op het My DHL Parcel-portaal en
ga naar **Settings → API Keys**. Hier maak je je credentials aan en kopieer
je drie waarden:

- **User ID** — een UUID zoals `87dcdd1b-0999-4d96-afaa-09f16a201263`
- **API Key** — een UUID
- **Account ID** — je korte DHL-klantnummer, bv. `40051608`

Deze drie waarden vul je later in op het DHL Parcel-tabblad van de
verzendmethode in Odoo.

### Verplichte JWT-rol: `label-service.B2X`

De API key moet deze rol bevatten in zijn JWT-token om labels te kunnen
aanmaken. Als je `"DHL Parcel rejected the shipment"`-errors krijgt die
over permissions gaan, is dit het eerste wat je laat verifiëren door DHL.

### Optionele zaken (per feature)

| Feature | Wat DHL moet voorzien |
|---|---|
| Cancellation via API | Niet ondersteund door de publieke API — alleen via het portaal |
| International routes (Parcel Connect, Europlus International) | De juiste contractproducten (CON / EPL-INT / EPL-PAL) |
| Returns (`returnLabel: true`) | Het overeenkomstige return-product (DFY-RETURN / EPL-RETURN / RETURN-CON) |

### Wat absoluut NIET via de API werkt

- **Live tarieven**. Bevestigd door DHL: hun gateway heeft geen
  rate-endpoint. Tarieven kan je enkel in het portaal bekijken (met de
  *Rate Manager*-rol). Prijzen op de Odoo-carrier ben je zelf
  verantwoordelijk voor.
- **Adresboek-export**. Het adresboek in My DHL Parcel is niet via de API
  toegankelijk.
- **Shipment-historiek opvragen**. De gateway is transactioneel
  (label aanmaken, één shipment ophalen), niet voor historische queries.

---

## 5. Installatie

### Vereisten

- Odoo 17 (community of enterprise)
- De `stock_delivery`-module (standaard meegeleverd in Odoo)
- Internet-toegang naar `api-gw.dhlparcel.nl`

### Installeren

Twee opties:

**Vanuit de Odoo UI:** Apps → Update Apps List → zoek *DHL Parcel Delivery
Carrier* → klik Install.

**Vanuit de command line:**
```bash
odoo-bin -d <database> -i delivery_dhl_parcel
```

### Optioneel maar aangeraden: Packages-feature aanzetten

Als je multicollo wil doen via Put in Pack (en niet alleen via het
*Aantal pakketten*-veld), zet de Packages-feature aan:

**Inventory → Configuration → Settings → Operations → Packages → Save.**

Zonder deze instelling is de knop "Put in Pack" niet zichtbaar op
deliveries.

### Module upgraden na een update

Telkens je een nieuwe versie van de module trekt (git pull of marketplace
update), ga je naar **Apps → DHL Parcel Delivery Carrier → Upgrade**. Een
gewone server-restart volstaat niet als er nieuwe velden of modellen bij
zijn gekomen.

---

## 6. Verzendmethodes aanmaken

### Strategie: per parceltype één methode + optioneel een MIX

Voor het courante geval maak je één Odoo-verzendmethode per DHL-parceltype
dat je wil aanbieden. Klanten (of jij in de backend) kiezen dan de methode
die overeenkomt met de gewenste pakketcategorie.

Een typische webshop-configuratie:

- **DHL Brievenbuspakket** (XSMALL, BE+NL)
- **DHL Pakket tot 10kg** (SMALL, alle 31 landen)
- **DHL Pakket tot 20kg** (SMALL_MEDIUM)
- **DHL Pakket tot 31kg** (MEDIUM)
- **DHL Pallet** (PALLET, alleen zakelijk)

Voor B2B-klanten waar één zending vaak meerdere pakkettypes bevat: maak
daarnaast een **DHL Gemengd**-methode aan, zie verder.

### Een methode aanmaken — stap voor stap

1. Ga naar **Inventory → Configuration → Shipping Methods → New**.
2. Geef de methode een herkenbare naam (bv. *DHL Pakket tot 10kg*).
3. Provider = **DHL Parcel (Benelux)**. Een tab **DHL Parcel** verschijnt.
4. Op de DHL Parcel-tab:
   - **Credentials** — User ID, API Key, Account ID. Dezelfde drie waarden
     voor al je DHL-methodes als ze dezelfde DHL-account delen. Multi-account
     setups: vul per methode de juiste creds in.
   - **Parcel type** — kies de DHL-categorie (bv. *Pakket tot 10kg*) of
     **Gemengd** voor een mix-methode.
   - **Default weight (kg)** — fallback-gewicht wanneer een pakket geen
     weight heeft. Default is 1 kg. DHL weigert een 0 kg-zending, dus dit
     veld voorkomt dat.
   - **Pricing mode** + **DHL flat price** of **Pricing rules** — zie
     sectie 7.
5. **Integration Level** (op de hoofdsectie van de carrier): laat op
   **Get Rate and Create Shipment**. Met *Get Rate* alleen wordt geen
   label gemaakt bij Validate.
6. **Countries**: kies de bestemmingen. De dropdown is automatisch beperkt
   tot de 31 ondersteunde landen, en verder ingeperkt op basis van het
   gekozen parceltype:
   - Envelop → alleen NL
   - Brievenbuspakket → alleen BE + NL
   - Pakket / Pallet → alle 31
7. Optioneel: **Website**. Bind de methode aan één webshop, of laat leeg
   om hem overal beschikbaar te maken.
8. **Delivery Product** — Odoo vereist een product dat de verzendkost
   vertegenwoordigt op het order. Maak er één aan (bv. *DHL Verzendkost*)
   of gebruik een bestaand verzendproduct. Zorg dat het product **geen
   specifieke Company** heeft (laat dat veld leeg) tenzij je per company
   apart wil werken.
9. **Save**.

### Bij MIX: parcel type = Gemengd

Specifiek voor de MIX-methode:

- De **Countries**-lijst toont alle 31 landen (geen type-restrictie op
  carrier-niveau, want types worden per parcel gekozen).
- **Pricing mode** en **Flat price** zijn verborgen — een MIX-methode
  gebruikt altijd de tarief-tabel.
- Er verschijnt een **extra notebook-tab "DHL Tarieven"**: vul daar voor
  elk parceltype de prijs in die je aan klanten aanrekent (komt uit je
  DHL-rate card). De zes types worden automatisch toegevoegd bij het
  kiezen van "Gemengd".

---

## 7. Prijszetting

De DHL Parcel-API geeft geen prijzen terug. De prijs op het order wordt
lokaal berekend op basis van wat je op de carrier instelt.

Drie modi:

### Flat price

Eén vaste prijs per zending, ongeacht gewicht of aantal pakketten. Goed
voor B2C-webshops met simpele tarifering.

**Configuratie:** Pricing mode = **Flat price**, en vul **DHL flat price**
in (bv. €4,85).

### Weight-based rules

Gewichtstaffel: je definieert prijzen op basis van het totale gewicht van
de zending. Onder elke drempel = prijs X, daarboven = prijs Y, enz.

**Configuratie:** Pricing mode = **Weight-based rules**. Op de
**Pricing**-tab definieer je price-rules met `weight` als variabele.

Voorbeeld:
| Variable | Operator | Value | Price |
|---|---|---|---|
| weight | <= | 2 | 4.85 |
| weight | <= | 10 | 6.50 |
| weight | <= | 20 | 9.80 |

### Per-type tarief (alleen voor MIX)

Bij een MIX-carrier wordt de verzendkost berekend als
`som(aantal × tarief_voor_type)` over alle parcels op de delivery. De
tarieven zet je in de tab **DHL Tarieven** op de carrier.

**Workflow**:
1. Vul de tarieven in op de carrier (eenmalig, bv. €4,85 voor Brievenbuspakket).
2. Order krijgt MIX-carrier via Add Shipping → prijs is initieel 0 (er zijn
   nog geen parcels gedefinieerd op de delivery).
3. Magazijn vult de DHL Parcels-tab in op de delivery.
4. Ga terug naar het order, klik **Add Shipping** opnieuw → de prijs wordt
   bijgewerkt op basis van de ingevulde parcels.
5. Validate de delivery.

> ⚠ Dit vraagt heen-en-weer tussen SO en delivery omdat de prijs pas
> bekend is na het magazijn-werk. Voor de simpele *Aantal pakketten*-flow
> hoeft dat niet — daar staat de prijs vast bij Add Shipping.

---

## 8. Dagelijkse workflow

Drie typische scenario's:

### A. Webshop B2C (volledig automatisch)

1. Klant plaatst order in de webshop, kiest een DHL-methode bij checkout.
2. Order krijgt automatisch een delivery-line met de juiste prijs en de
   `carrier_id` is gezet.
3. Bij confirmatie van het order krijgt de gegenereerde delivery dezelfde
   carrier.
4. Magazijn raapt uit en valideert de delivery → label wordt aangemaakt.

Geen extra clicks nodig — de Add Shipping-stap is impliciet in checkout.

### B. Backend B2B met prepaid shipping (Add Shipping op het order)

1. Verkoper maakt SO aan in de backend.
2. Klik **Add Shipping** op de SO → kies de juiste DHL-methode → wizard
   voegt delivery-line toe met de prijs.
3. Confirm de SO → delivery wordt aangemaakt met dezelfde carrier.
4. Magazijn raapt uit en valideert → label wordt aangemaakt.

Voor uniforme zendingen (één parceltype, één of meerdere identieke
pakketten): zet eventueel **Aantal pakketten** op de delivery, vóór
Validate.

### C. Backend B2B met facturatie achteraf

Sommige B2B-klanten worden gefactureerd na verzending. Dan kan je
helemaal zonder Add Shipping werken:

1. SO heeft geen carrier en geen shipping-line.
2. Magazijn opent de delivery, zet de **Carrier** in de *Additional Info*-tab.
3. Vult eventueel **Aantal pakketten** of DHL Parcels-tab in.
4. Valideert → label wordt aangemaakt.
5. Verzendkost wordt handmatig op de eindfactuur gezet.

> Let op: in deze flow staat er geen verzendkost-line op de SO. Als je
> later toch Add Shipping doet op de SO, kan dat een andere carrier kiezen
> dan wat op de picking staat. Houd discipline of werk consistent in één
> flow.

---

## 9. Multicollo (meerdere pakketten in één zending)

Er zijn drie manieren om aan te geven dat een delivery uit meerdere
pakketten bestaat. Welke je gebruikt hangt af van de situatie.

### Optie 1: Aantal pakketten (eenvoudigst, identieke pakketten)

**Wanneer:** je verzendt N identieke pakketten van het type van de
carrier. Bv. *3 brievenbuspakketten* of *2 Pakketten tot 10kg*. Het
maakt niet uit welk artikel in welk pakket zit (boekjes, dvd's, ...).

**Hoe:** op de delivery zie je naast de Carrier een veld **Aantal
pakketten**. Default 1. Zet er bv. `3` in en bewaar.

**Resultaat:** Eén DHL-shipment met 3 pieces, allemaal van het type van
de carrier. DHL geeft 3 trackers en één multipage PDF met 3 labels.

### Optie 2: Put in Pack (gemengde inhoud, identiek type)

**Wanneer:** je wil specifieke artikelen in specifieke dozen stoppen
(bv. fragiele items apart), maar alle dozen zijn van hetzelfde type.

**Hoe:** zie sectie 10.

### Optie 3: MIX-carrier + DHL Parcels-tab (verschillende types)

**Wanneer:** je hebt verschillende parceltypes in één zending nodig.
Bv. 2 brievenbuspakketten + 1 pakket tot 10kg in één levering.

**Hoe:**
1. Gebruik een **MIX-carrier** (parcel type = Gemengd).
2. Op de delivery verschijnt een tab **DHL Parcels**. Voeg één regel per
   pakket toe: type + aantal + (optioneel) gewicht.
3. De type-lijst past zich automatisch aan: een particuliere ontvanger
   ziet Envelop/Brievenbus/Pakket; een zakelijke ontvanger ziet
   Pakket/Pallet.
4. Validate → DHL maakt één shipment met de gespecificeerde pieces.

---

## 10. Put in Pack — uitgelegd

**Put in Pack** is Odoo's mechanisme om de items van een delivery in één
of meerdere *packages* (dozen) te organiseren. Voor onze module gebruik
je het om aan te geven *welke specifieke items in welke specifieke doos
gaan*.

### Hoe het werkt

Een delivery heeft één of meer **move lines**: de regels die zeggen "X
stuks van product Y". Bovenaan op de delivery zie je deze regels met een
*Demand* (gevraagde quantity) en een *Done* (effectief uitgeraapte
quantity).

Wanneer je op **Put in Pack** klikt:
1. Odoo neemt **alle huidige Done quantities** die nog niet in een pack
   zitten.
2. Maakt daar één `stock.quant.package` (pakket) van.
3. Hangt die package aan de move lines.

Een Done = 0 op een regel betekent: die regel gaat (nu nog) niet in dit
pakket.

### Voorbeeld — 1 pakket met alles

Je hebt een delivery met 5× *Boek A* en 3× *Boek B*. Beide regels staan
op Done = 5 en Done = 3 (standaard: alles is "klaar"). Eén klik op Put
in Pack → alle 8 items zitten in pack 1. Klaar.

### Voorbeeld — 2 pakketten, met items verdeeld

Je wil 3× Boek A in pakket 1, en 2× Boek A + 3× Boek B in pakket 2.

1. Open de delivery, ga naar **Detailed Operations** (of klik op de regel
   om de quantities te zien).
2. Op de regel van Boek A: zet **Done** op `3` (in plaats van de volle 5).
3. Op de regel van Boek B: zet **Done** op `0`.
4. Klik **Put in Pack** → pack 1 wordt aangemaakt met 3× Boek A.
5. Nu zet je op de Boek A-regel **Done** = `2` (de resterende), en op Boek
   B = `3`.
6. Klik **Put in Pack** → pack 2 met 2× Boek A + 3× Boek B.

### Veelvoorkomende fout

> **"Invalid Operation: There is nothing eligible to put in a pack."**

Dit betekent: er zijn momenteel geen Done-quantities die nog niet in een
pack zitten. Oplossing: ga naar Detailed Operations en zet wat extra Done
op de regels die je in een volgend pakket wil stoppen.

### Wanneer GEEN Put in Pack gebruiken

- **Alle pakketten zijn identiek qua inhoud-type**: gebruik gewoon
  *Aantal pakketten* op de delivery. Veel minder klikken.
- **Verschillende parceltypes in één zending**: gebruik een MIX-carrier
  + de DHL Parcels-tab. Daar geef je per parcel een type op, zonder
  Put-in-Pack.

### Wat onze module doet met packages

Wanneer je Validate doet:
- Als de delivery packages heeft (via Put in Pack): één DHL-piece per
  package, met het type van de carrier en het gewicht van de package.
- Als er geen packages zijn maar wel een MIX-carrier met DHL Parcels-regels:
  één piece per regel, met het opgegeven type en aantal.
- Anders: één piece met `quantity = Aantal pakketten` (default 1).

---

## 11. Het label en de tracking

Wanneer je een DHL-delivery valideert:

1. De module roept de DHL-API aan om de shipment aan te maken.
2. DHL geeft per piece een **trackerCode** terug.
3. De module haalt het label (PDF) op.
4. **De PDF wordt als attachment aan de delivery gehangen.** Eén PDF, ook
   bij multicollo (alle labels zitten in dezelfde multipage PDF).
5. **De tracker-codes** komen op `carrier_tracking_ref` van de picking
   (komma-gescheiden bij meerdere pieces).

Het label opzoeken: open de delivery → tab "Documenten" of het paperclip-
icoon → de PDF heet typisch `DHL-<shipmentId>.pdf`. Print en plak op de
dozen.

Track & trace voor je klant: DHL's publieke tracker-pagina is
`https://www.dhlparcel.nl/nl/consument/traceer-uw-zending?tt=<trackerCode>`.

---

## 12. Annuleren

> **Annuleren gebeurt altijd in het My DHL Parcel-portaal.**
> DHL's publieke API biedt geen endpoint om shipments programmatisch te
> annuleren. Hun OpenAPI-spec heeft alleen een read-only
> `GET /intervention-options` om te checken of een cancel toegestaan zou
> zijn, maar geen POST om de cancel effectief uit te voeren. Dit is geen
> tijdelijke beperking — zo is het ontwerp van de Business API.

De cancel-actie in Odoo:
- Verwijdert geen tracking-referentie (zodat je nog steeds weet welk
  shipment je moet annuleren).
- Plaatst een chatter-note op de delivery met de instructie om in het
  portaal te annuleren.
- Roept de DHL-API niet aan.

**Wat je moet doen:** log in op My DHL Parcel, zoek de shipment via z'n
tracker-code, en annuleer 'm daar.

---

## 13. Wat als het misgaat

Een lijst van de meest voorkomende fouten en wat ze betekenen:

### Bij het opslaan van een carrier

> **"Kies een Parcel type op de DHL-verzendmethode '...'"**

Het Parcel type-veld is verplicht voor DHL-carriers. Kies er één.

> **"DHL Parcel verzendt niet naar de volgende landen: ..."**

Je hebt een land in de Countries-lijst staan dat DHL Parcel niet bedient.
Verwijder het.

> **"Het parceltype '...' is enkel beschikbaar voor zendingen naar ..."**

Type-vs-land mismatch. Bv. Envelop = alleen NL, Brievenbuspakket = alleen
BE+NL. Pas de Countries aan of kies een ander type.

### Bij het valideren van een delivery

> **"De delivery heeft geen klantadres."**

`partner_id` is leeg op de picking. Stel een Customer in.

> **"Customer '...' heeft geen land ingesteld."**

Zet een land op de partner.

> **"Customer '...' address is incomplete (street / zip / city required)."**

Vul Street, ZIP en City aan op de partner.

> **"The warehouse / company address is incomplete"**

Je magazijn (`stock.warehouse.partner_id`) of company-adres mist gegevens.
Vul aan: street, zip, city, country.

> **"Het parceltype '...' is enkel beschikbaar voor particuliere
> ontvangers. '...' is een bedrijf."**

Je hebt een consumer-only type (Envelop, Brievenbuspakket) gekoppeld aan
een carrier en die wordt gebruikt voor een zakelijk klantadres. Gebruik
een ander type of een andere carrier.

> **"Voeg minstens één parcel toe in de DHL Parcels-tab op deze delivery"**

Je valideert een MIX-delivery zonder regels in de DHL Parcels-tab. Vul
de tab in.

> **"DHL Parcel rejected the shipment (HTTP 400): capabilities_retrieve_empty"**

DHL kon geen product/route/type-combo matchen. Meest waarschijnlijk:
parceltype past niet bij de ontvanger (consumer-only naar bedrijf, of
omgekeerd). Lokale guards vangen dit normaal op vóór de API-call.

### Authenticatie / permissions

> **"DHL Parcel authentication returned no accessToken"**

Verkeerde User ID of API Key. Controleer beide in My DHL Parcel.

> **HTTP 401/403 errors over labels**

Je API Key mist de rol `label-service.B2X`. Contacteer DHL.

### Browser-cache

> **"Invalid field '...' on model 'delivery.carrier'"** of vergelijkbaar

Meestal browser-cache van een oude view. Hard refresh (Ctrl+Shift+R) of
clear site data in dev-tools. Als dat niet helpt: heb je de module
upgraded na de laatste code-update?

---

## 14. Talen

De module is beschikbaar in:

- **Nederlands** (broncode)
- **Engels** (`i18n/en.po`)
- **Frans** (`i18n/fr.po`)
- **Duits** (`i18n/de.po`)

De getoonde taal volgt de **user language** van de Odoo-gebruiker. Wijzig
in **Preferences → Language**.

Heb je een andere taal nodig die niet meegeleverd wordt? Je kan binnen
Odoo zelf strings vertalen via **Settings → Translations → Translated
Terms**, gefilterd op de module. Deze vertalingen gelden voor jouw
database; ze worden niet automatisch in de module opgenomen.

---

## 15. Korte FAQ

**Heb ik een delivery-product nodig?**
Ja. Odoo eist dat elke carrier een delivery-product heeft (waarop de
verzendkost als orderline geboekt wordt). Maak er één aan zoals *DHL
Verzendkost*. Laat de Company leeg tenzij je per company een aparte wil.

**Mijn carrier is niet zichtbaar bij Add Shipping.**
Twee oorzaken meest voorkomend: (1) destination van het order valt
buiten de Countries-lijst van de carrier; (2) company-mismatch — de
carrier erft z'n company van het delivery-product; check daar de Company.

**Kan ik verzenden vanuit Duitsland of Spanje?**
Niet met deze module. Je verzender moet in BE, NL of LU zitten. Voor
verzenden vanuit een ander land heb je een DHL-contract van die regio
nodig (DHL Parcel DE, ES, ...) en een passende module.

**Werkt de module met multi-company?**
Ja. Credentials staan per carrier, dus elke company kan z'n eigen
DHL-account hebben. Eén database kan dus drie DHL-accounts dienen
(één per company).

**Hoe weet ik welk parceltype past bij wat ik verzend?**
DHL's regels:
- *Envelop* (max 500g, NL only): brieven, kleine documenten.
- *Brievenbuspakket* (max 2kg, BE/NL, B2C): kleine pakketten die door de
  brievenbus passen.
- *Pakket tot 10/20/31 kg*: standaardpakketten, dimensies tot 80x50x35cm.
- *Pallet tot 1000 kg*: alleen B2B, voor zware zendingen.

**Test- versus productie-omgeving?**
DHL Parcel gebruikt één API-adres voor beide. Of je in test of live zit
bepaalt alleen welke API key je invoert. De *Test Environment*-knop op
de carrier doet voor deze provider niets.

---

## Bijlage A — Ondersteunde bestemmingen (31 landen)

Voor verzenders in BE, NL of LU:

België, Bulgarije, Denemarken, Duitsland, Estland, Finland, Frankrijk,
Griekenland, Groot-Brittannië, Hongarije, Ierland, Italië, Kroatië,
Letland, Liechtenstein, Litouwen, Luxemburg, Monaco, Nederland,
Noorwegen, Oostenrijk, Polen, Portugal, Roemenië, San Marino, Slovenië,
Slowakije, Spanje, Tsjechië, Zweden, Zwitserland.

Retours komen vanuit dezelfde 31 landen terug naar je Benelux-magazijn.
