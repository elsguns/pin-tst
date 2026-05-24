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
