"""
Anti-Corruption Layer (ACL) for the Lending bounded context.

The ACL protects the Lending context from being corrupted by the models
and concepts of upstream contexts (Catalog and Patron). It acts as a
translator between the external world and our internal domain model.

Why do we need an ACL?
----------------------
1. Upstream contexts may change their models - ACL isolates us from those changes
2. Upstream contexts use different terminology - ACL translates to our language
3. Upstream contexts may have different data structures - ACL adapts them

Components:
-----------
- CatalogACL: Translates Catalog context data for use in Lending
- PatronACL: Translates Patron context data for use in Lending

Example flow:
-------------
1. Use case needs to borrow a book for a patron
2. Use case calls PatronACL.get_borrower_info(patron_id)
3. ACL fetches from Patron context and translates to Lending's BorrowerInfo
4. Use case calls CatalogACL.get_book_for_lending(book_id)
5. ACL fetches from Catalog context and translates to Lending's BookReference
6. Use case creates a Loan using the translated data
"""
from .catalog_acl import BookReference, CatalogACL
from .patron_acl import BorrowerInfo, PatronACL

__all__ = [
    "CatalogACL",
    "BookReference",
    "PatronACL",
    "BorrowerInfo",
]
