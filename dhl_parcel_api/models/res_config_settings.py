from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    dhl_parcel_user_id = fields.Char(
        string="User ID",
        config_parameter="dhl_parcel_api.user_id",
    )
    dhl_parcel_api_key = fields.Char(
        string="API Key",
        config_parameter="dhl_parcel_api.api_key",
    )
    dhl_parcel_account_id = fields.Char(
        string="Account ID",
        config_parameter="dhl_parcel_api.account_id",
        help="Short DHL account number, e.g. 08500001.",
    )

    dhl_parcel_shipper_company = fields.Char(
        string="Shipper Company",
        config_parameter="dhl_parcel_api.shipper_company",
    )
    dhl_parcel_shipper_street = fields.Char(
        string="Shipper Street",
        config_parameter="dhl_parcel_api.shipper_street",
    )
    dhl_parcel_shipper_number = fields.Char(
        string="Shipper Number",
        config_parameter="dhl_parcel_api.shipper_number",
    )
    dhl_parcel_shipper_postal_code = fields.Char(
        string="Shipper Postal Code",
        config_parameter="dhl_parcel_api.shipper_postal_code",
    )
    dhl_parcel_shipper_city = fields.Char(
        string="Shipper City",
        config_parameter="dhl_parcel_api.shipper_city",
    )
    dhl_parcel_shipper_country_code = fields.Char(
        string="Shipper Country Code",
        config_parameter="dhl_parcel_api.shipper_country_code",
        help="ISO-2 country code, e.g. BE.",
    )
    dhl_parcel_shipper_phone = fields.Char(
        string="Shipper Phone",
        config_parameter="dhl_parcel_api.shipper_phone",
    )
    dhl_parcel_shipper_email = fields.Char(
        string="Shipper Email",
        config_parameter="dhl_parcel_api.shipper_email",
    )
