"""Small explicit vocabulary, not unrestricted natural-language interpretation.
Only whole affirmative statements are recognized, with exact source pointers.
Unknown wording never establishes a guarantee.
"""
import re

STATEMENTS = {
 'deletion_preserves_others': 'deletion preserves non-target resources',
 'creation_visible': 'creation is synchronously visible',
 'deletion_removes': 'completed deletion removes the exposed resource',
 'rejected_create_no_effect': 'rejected creations preserve business state',
 'failed_write_no_effect': 'failed writes preserve business state',
}


def derive_policies(doc):
    description = doc.get('info', {}).get('description', '')
    sentences = {s.strip().lower() for s in re.split(r'[.;\n]', description)} if isinstance(description, str) else set()
    return {key: {'pointer': '#/info/description', 'statement': phrase,
                  'basis': 'exact_affirmative_contract_statement'}
            for key, phrase in STATEMENTS.items() if phrase in sentences}
