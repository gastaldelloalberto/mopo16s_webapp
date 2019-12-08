from Bio.SeqIO import parse as fasta_parse
from io import StringIO, TextIOWrapper
from django.forms import ValidationError


def dummy_callback(_):
    return


def validate_fasta(handler, callback=dummy_callback):
    # count valid sequences
    n = 0
    for record in fasta_parse(handler, 'fasta'):
        if not record.seq:
            n = 0
            break
        callback(record.format('fasta'))
        n += 1
    
    if n == 0:
        raise ValidationError('Invalid FASTA format.', code='invalid')
    return n


def validate_fasta_str(text, *args, **kwargs):
    return validate_fasta(StringIO(text), *args, **kwargs)


def validate_fasta_file(text, *args, **kwargs):
    return validate_fasta(TextIOWrapper(text), *args, **kwargs)
