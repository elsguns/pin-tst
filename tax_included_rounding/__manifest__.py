{
    'name': 'Tax Included Rounding Fix',
    'version': '17.0.2.0.2',
    'category': 'Accounting',
    'summary': 'Fix VAT rounding for tax-included prices',
    'description': """
        Deze module corrigeert de BTW-berekening voor prijzen inclusief BTW.
        
        PROBLEEM:
        Odoo berekent standaard de BTW per orderregel en telt die op. Door 
        afrondingsverschillen per regel kloppen de totalen op de factuur niet:
        Totaal excl. BTW + BTW ≠ Totaal incl. BTW.
        
        OPLOSSING:
        Deze module berekent het andersom, per BTW-tarief:
        1. Totaal incl. BTW = som van alle regelbedragen (per tarief)
        2. Totaal excl. BTW = Totaal incl. BTW ÷ (1 + tarief)
        3. BTW = Totaal incl. BTW - Totaal excl. BTW
        
        Zo kloppen de drie bedragen op de factuur altijd.
        
        MEERDERE BTW-TARIEVEN:
        De module ondersteunt orders/facturen met meerdere BTW-tarieven 
        (bv. 6% én 21%). De berekening wordt per tarief uitgevoerd en 
        daarna opgeteld.
        
        BEPERKINGEN:
        - Werkt alleen voor prijzen inclusief BTW (price_include = True)
        - Werkt alleen voor percentage-gebaseerde BTW (niet voor vaste bedragen)
        - Bij regels zonder BTW valt de module terug op standaard Odoo-berekening
    """,
    'author': 'Custom',
    'depends': ['sale', 'account'],
    'data': [],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
