# DHL Parcel Delivery Carrier: Configuration and FAQ

This document lists everything that must be configured for the module to work,
the data in Odoo it depends on, and the questions that come up most often. It is
meant to grow into the customer-facing FAQ.

## Prerequisites

- Odoo 17 with the delivery features installed (the module depends on
  `stock_delivery`).
- An active DHL Parcel (DHL eCommerce Benelux) business account that has API
  access enabled.
- API credentials: a **User ID** and an **API Key**, plus the short **Account
  ID** (customer number). See "Where do I get the API credentials?" below.
- To ship a delivery as several parcels (multicollo), either use the
  **Aantal pakketten** field on the delivery (simplest, one DHL piece with
  quantity=N) or enable the **Packages** feature (Inventory > Configuration
  > Settings > Operations > Packages) and use **Put in Pack** to split items
  per box. With Put in Pack, each package becomes a separate piece.

## Setting up the shipping method

Create **one shipping method per parcel type** you want to offer (Brievenbus-
pakket, Pakket tot 10kg, Pakket tot 20kg, ...). Each method represents one
fixed DHL parcel type with its own pricing.

1. Install the module **DHL Parcel Delivery Carrier**.
2. Go to **Inventory > Configuration > Shipping Methods** and create a new one.
3. Set **Provider** to **DHL Parcel (Benelux)**. A **DHL Parcel** tab appears.
4. On that tab, fill in:
   - **Credentials**: User ID, API Key, Account ID.
   - **Parcel type** (required): the DHL type for all shipments under this
     method, e.g. Brievenbuspakket or Pakket tot 10kg.
   - **Default weight (kg)**: the weight sent when a parcel has none (see FAQ).
   - **Pricing mode**: Flat (with a flat price) or Weight-based rules.
5. Leave **Integration Level** on **Get Rate and Create Shipment**. This is
   required for a label to be created when a delivery is validated.
6. **Countries**: pick the destinations this method covers. The list is
   automatically restricted to the 31 countries DHL Parcel delivers to, and
   further narrowed by the chosen parcel type (ENVELOPE: NL only;
   Brievenbuspakket: BE+NL only).
7. Optional: **Website**. Bind the method to one website for webshop checkout,
   or leave it empty to make it available everywhere.

## DHL-side permissions and feature gating

Beyond the credentials, several features depend on what DHL has activated on
your API key and contract. Most are arranged once during onboarding; ask your
DHL technical contact when in doubt.

**Required for the basic flow (creating labels):**
- The API key's JWT token must include the role **`label-service.B2X`**. Without
  it, label creation fails. If the module reports authentication or "rejected
  the shipment" errors that mention permissions, this is the first thing to
  verify with DHL.

**Not available at all:**
- **Live pricing via the API.** Confirmed with DHL: the gateway has no rating
  endpoint, and the `price` field that appears in the `/parcel-types` schema is
  meant for customs declarations (currency + declared value), not for tariff
  lookup. Tariffs can be viewed in the My DHL Parcel portal (requires the Rate
  Manager role on your account) but cannot be fetched programmatically. The
  module therefore uses the carrier's configured price (flat amount or
  weight-based rules) for shipping cost on the sale order.

- **Cancellation via API.** DHL's public API has no documented endpoint for
  cancelling a shipment programmatically. Their OpenAPI spec covers
  `GET /intervention-options` (to ask whether interventions are available)
  but provides no POST endpoint for actually executing a cancel. Cancellation
  is meant to happen in the My DHL Parcel portal. The module's cancel action
  reflects this: it posts a chatter note on the delivery telling the operator
  to cancel in the portal, and leaves the local tracking reference in place
  so the operator can look it up. This is not a temporary limitation — it is
  how the public API is shaped.

**Optional, each gated by a separate DHL-side setting:**

- **International shipping** (Parcel Connect / Europlus / Europlus Pallet /
  Europlus International). These require the corresponding products to be part
  of your DHL contract. Confirm with DHL which products are active on your
  account before configuring the module for non-Benelux destinations.

- **Returns** (`returnLabel: true` and the `ADD_RETURN_LABEL` option). The
  `/shipments` endpoint accepts these without an extra permission, provided
  your DHL contract includes the relevant return product (DFY-RETURN /
  EPL-RETURN / RETURN-CON).

**How the module behaves when a permission is missing:**
- No `label-service.B2X`: a clear UserError points to credentials/permissions.
- Cancel action: always posts a chatter note ("cancel in the portal"); never
  calls the API. See above for why.
- Contract gaps (missing product, missing route): the API's own error message
  is surfaced verbatim in the chatter, which usually identifies the contract
  issue.

**If you suspect a permission issue:**
The roles on your token can be inspected by enabling debug logging on the
`delivery_dhl_parcel` logger and inspecting the authentication response. Share
the list of roles you have with your DHL tech contact and ask which additional
role activates the missing feature.

## Required data in Odoo (often missed)

- **The warehouse address must be complete** (company name, street, house
  number, postal code, city, country). It is printed on the label as the sender
  and is used for returns. An incomplete warehouse address blocks shipment
  creation.
- **Product weights**: products should carry a weight. Without it the parcel
  weight is 0, which DHL rejects. See the FAQ entry on the default weight.
- **Customer address**: the house number is read from the **street2** field
  (Belgian convention) or parsed from the end of **street**. A missing house
  number causes DHL to flag the shipment for manual check.
- All address fields must use the **Latin alphabet** only. This is a DHL
  constraint.

## FAQ

**The package cannot be created because the total weight of the products in the
picking is 0.0 kg.**
The products have no weight set, so Odoo will not build a package. Either set
weights on the products, or rely on the carrier's **Default weight (kg)** field,
which is sent when the parcel weight is 0. Note that an inaccurate declared
weight can lead DHL to re-weigh the parcel and adjust the invoice.

**How is the parcel type chosen?**
The parcel type is fixed by the shipping method. Each method represents one
DHL parcel type (Brievenbuspakket / Pakket tot 10kg / ... / Pallet tot 1000kg),
so the type is decided when you (or the customer) pick the method. Create one
shipping method per type you want to offer. A regular parcel maxes at 31 kg;
above that, use a Pallet method.

For shipments that mix parcel types in one delivery (like the My DHL Parcel
portal supports), create a method with **Parcel type = Gemengd (MIX)**. On
deliveries using that method a **DHL Parcels** tab appears where you add one
row per parcel, picking the type per row. The type list adapts to whether the
recipient is a private person or a business.

**Where do I set the shipping price? The Fixed Price field seems ignored.**
The DHL Parcel API does not return live rates, so the price is set on the
carrier itself. Choose **Pricing mode = Flat** and fill in **DHL flat price**,
or **Pricing mode = Weight-based rules** and define the tiers on the **Pricing**
tab (use `weight` as the variable). The generic "Fixed Price" field of the base
carrier is not used by this provider.

**The DHL method is missing / I can't select it on a delivery.**
A shipping method is filtered by company: its Company is **inherited from its
delivery product**, so you can't change it on the carrier directly. If the
delivery product has a company set, the carrier only appears for that company's
deliveries. Fix: open the delivery product and clear its Company (blank = all
companies), or set it to the company you ship from. Destination country also
matters: the method only offers itself for the countries listed on the carrier.

**Nothing happens when I validate the delivery.**
Check that **Integration Level** is set to **Get Rate and Create Shipment**.
With "Get Rate" only, no label is created on validation.

**What does the Test Environment / Production Environment button do?**
Nothing, for this provider. DHL Parcel uses a single API address for both test
and production. Whether you are in test or live depends only on which API key
you enter.

**Can I set a default shipping method on orders?**
Set the **Delivery Method** field on the customer (Contacts > customer > Sales
and Purchase tab). New orders for that customer then default to it. There is no
single global default for all orders without customization. For webshop orders
the customer chooses the method at checkout.

**One order ships from two warehouses. What happens?**
Odoo creates a separate delivery per warehouse, and each becomes its own DHL
shipment with its own correct sender address. A single label can carry only one
sender, so different warehouses always mean different shipments.

**How do I quickly declare several parcels?**
On a DHL delivery there is an **Aantal pakketten** field. Set it to the number
of identical parcels you want to ship; the module sends one DHL shipment with
that many pieces, all of the carrier's parcel type. DHL returns one tracker
per piece and one combined multi-page label PDF. No need to use Put in Pack
when all pieces are the same type.

**I don't see a "Put in Pack" button on the delivery.**
Enable the Packages feature: Inventory > Configuration > Settings > Operations >
Packages, then save. The button appears on the delivery afterwards.

**How do I put some products in one box and the rest in another?**
Odoo packs by quantity. In Detailed Operations, set the quantity only on the
lines for the first box (set the others to 0), click Put in Pack, then set the
remaining lines and Put in Pack again. Each Put in Pack bundles whatever
currently has a quantity and is not yet packed.

**The Package Type dropdown is empty.**
That is fine; package type is not used by this module. The DHL parcel type is
fixed by the shipping method.

**An order is packed in several boxes (with different items per box).**
Use native **Put in Pack**: split the quantities so the items for box 1 are
"Done" first, click Put in Pack, then set the remaining quantities and Put in
Pack again. Each package becomes one piece in the DHL shipment, all of the
carrier's parcel type. Each piece gets its own tracking code, and all labels
come back in one multi-page PDF attached to the delivery. When you don't care
which items go in which box, use the **Aantal pakketten** field instead
(simpler — one click).

**Which destinations can I ship to?**
Benelux works now: BE, NL and LU are all handled by the default flow. DHL
resolves the correct product automatically (DFY or Europlus for NL, Parcel
Connect or Europlus for LU) and the parcel-type tiers are available. Set the
carrier's Countries to BE, NL, LU.

Shipping beyond Benelux (DE, FR, GB, ...) is a separate, not-yet-built feature.
Those routes use different products (DHL Parcel Connect, Europlus International,
Europlus Pallet) and, for non-EU destinations such as GB, a customs
declaration. It also depends on your DHL contract including those products.

**Does the parcel type depend on whether the customer is a person or a company?**
No. DHL's parcel-type catalog is the same regardless of recipient; the
business-versus-consumer difference is handled by the product DHL selects
automatically (a home-delivery product for consumers, a business product
otherwise).

**How do I cancel a shipment?**
In the My DHL Parcel portal — there is no programmatic alternative. DHL's
public API has no cancel endpoint, only a read-only `GET /intervention-options`
that reports whether a cancel would be allowed. The module's cancel action
posts a note on the delivery (with the tracking reference still readable so
you can look it up in the portal).

Note from DHL: a label that was created but the parcel never entered DHL's
network (i.e. you cancelled before drop-off) is not billed. You only need to
cancel in the portal if you want the shipment removed from your MDP
shipment list for housekeeping.

**Do shipments created via the API appear in the DHL dashboard?**
This is account dependent and should be confirmed with DHL for the specific
contract.

**The portal has a "save this customer" tickbox when entering a shipment.
Does the module use it?**
No, and it cannot: DHL Parcel's public API has no address-book / customer
endpoints. The "save customer" tickbox in My DHL Parcel is a portal-internal
feature that only matters when you enter shipments manually through the
portal UI. In our flow, Odoo's `res.partner` records are the customer
database: each delivery sends its receiver address straight from the partner
to DHL, so there is no need for a second copy of the address living in
DHL's portal. The tickbox can safely be ignored when using this module.

**Where do I get the API credentials?**
From the My DHL Parcel / DHL eCommerce portal, under Settings > API Keys. If the
portal only shows a "Connections" page and no API Keys section, ask the DHL
contact to provision API access for the account. The Account ID is the short
customer number visible on invoices and in the account details.

## Notes for the integrator

- Credentials live on the shipping method record, not in global settings, so a
  single Odoo database can serve several DHL accounts (one carrier each).
- The shipper address comes from the originating warehouse in Odoo, not from the
  DHL dashboard default. This keeps multi-warehouse and returns correct.
- The label PDF is fetched from DHL and attached to the delivery as is. The
  module does no label rendering, so any DHL label layout change is picked up
  automatically.
