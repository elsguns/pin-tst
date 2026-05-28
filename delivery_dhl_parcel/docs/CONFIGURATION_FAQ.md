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
- To ship a delivery as several parcels (multicollo), enable the **Packages**
  feature: Inventory > Configuration > Settings > Operations > Packages. Without
  it there is no "Put in Pack" button and every delivery is a single parcel.

## Setting up the shipping method

1. Install the module **DHL Parcel Delivery Carrier**.
2. Go to **Inventory > Configuration > Shipping Methods** and create a new one.
3. Set **Provider** to **DHL Parcel (Benelux)**. A **DHL Parcel** tab appears.
4. On that tab, fill in:
   - **Credentials**: User ID, API Key, Account ID.
   - **Default parcel type** (usually SMALL).
   - **Default weight (kg)**: the weight sent when a parcel has none (see FAQ).
   - **Pricing mode**: Flat (with a flat price) or Weight-based rules.
5. Leave **Integration Level** on **Get Rate and Create Shipment**. This is
   required for a label to be created when a delivery is validated.
6. **Countries**: scope the method to the destinations the account supports
   (currently Benelux, see "Can I ship outside Benelux?").
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

**Optional, each gated by a separate DHL-side setting:**

- **Live pricing in API responses.** The `/parcel-types` endpoint has a `price`
  field in its schema, but it is only returned when DHL has activated pricing
  visibility on the API key. Without it, the module uses the carrier's
  configured price (flat amount or weight rules) instead of fetching live
  rates. Ask DHL whether pricing visibility can be enabled on your key.

- **Cancellation via API** (`/interventions/cancel`). The exact endpoint and
  request body must be obtained from your DHL tech contact, and the API key
  needs the matching intervention role. Until that is in place, the module's
  cancel action only clears the local tracking reference and posts a chatter
  note advising you to cancel the shipment in the DHL portal. No API call is
  attempted, so nothing fails.

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
- No live pricing: the configured flat/weight-rule price is used silently. No
  failure.
- No cancel permission: the cancel action posts a clear chatter note ("DHL
  cancellation API not integrated yet, please cancel in the portal"). No
  silent failure.
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
By default the module picks it automatically from each parcel's weight, using
the DHL Belgium tiers: up to 10 kg = Small, 10-20 kg = Small-Medium, 20-31 kg =
Medium, above 31 kg = Pallet. (XSmall / mailbox is never auto-selected because
it also has a tiny size limit; choose it explicitly if you need it.) To force a
single type for every parcel, set the Parcel type field on the carrier; leave it
empty for automatic selection. A regular parcel maxes at 31 kg, so a heavier
shipment must be packed into several boxes (each box becomes one piece).

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

**How do I quickly declare several parcels (the portal-style way)?**
On a DHL delivery there is a **DHL Parcels** tab. Add one row per parcel, just
like the My DHL Parcel portal: pick the parcel type, set the quantity, and
optionally a weight (if left blank, a weight matching the chosen type is sent,
so a "Parcel up to 31 kg" is not declared as 1 kg). The parcel-type list adapts to the customer (a person sees
envelope / mailbox / parcel options; a company sees parcel / pallet options).
The shipment is created with exactly those parcels. This avoids the Put-in-Pack
splitting work; it is the fastest way to ship one order as several boxes. Leave
the table empty to fall back to the delivery's packages, or to a single parcel.

**I don't see a "Put in Pack" button on the delivery.**
Enable the Packages feature: Inventory > Configuration > Settings > Operations >
Packages, then save. The button appears on the delivery afterwards.

**How do I put some products in one box and the rest in another?**
Odoo packs by quantity. In Detailed Operations, set the quantity only on the
lines for the first box (set the others to 0), click Put in Pack, then set the
remaining lines and Put in Pack again. Each Put in Pack bundles whatever
currently has a quantity and is not yet packed.

**The Package Type dropdown is empty.**
That is fine; package type is optional. The module decides the DHL parcel type
from each package's weight, not from the package type, so you can leave it empty.
(Defining stock.package.type records is only needed if you want to manage box
dimensions explicitly.)

**An order is packed in several boxes.**
Put the items into packages on the delivery (native "Put in Pack"). The module
then creates **one DHL shipment with one piece per package** (multicollo): each
piece gets its own tracking code, and all labels come back in a single
multi-page PDF attached to the delivery. One delivery is one shipment in the DHL
dashboard, with N parcels under it. A parcel is only split into multiple pieces
when you actually pack it into multiple boxes; a single light order stays one
piece.

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
otherwise). So you do not configure separate parcel types per recipient type.

**How do I cancel a shipment?**
For now, in the DHL portal. The module's cancel action clears the local tracking
reference and posts a note on the delivery; it does not call DHL's cancellation
API yet.

**Do shipments created via the API appear in the DHL dashboard?**
This is account dependent and should be confirmed with DHL for the specific
contract.

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
