"""Minimal, independent FASTQ/QUAST readers for AGORA challenge extension."""
import csv
import gzip

QUAST_FIELDS = {
    '# contigs': 'contig_count',
    'Largest contig': 'largest_contig_bp',
    'Total length': 'assembly_length_bp',
    'GC (%)': 'gc_percent',
    'N50': 'n50_bp',
    'L50': 'l50',
}


def read_quast(path):
    result = {}
    with open(path, newline='', encoding='utf8') as file:
        reader = csv.reader(file, delimiter='\t')
        head = next(reader, None)
        if not head or len(head) != 2 or head[0] != 'Assembly':
            raise ValueError('Expected single-assembly reference-free QUAST report')
        for row in reader:
            if len(row) == 2 and row[0] in QUAST_FIELDS:
                name = QUAST_FIELDS[row[0]]
                if name in result:
                    raise ValueError('Repeated QUAST key: ' + name)
                result[name] = (float(row[1]) if name == 'gc_percent' else int(row[1].replace(',','')))
    if set(result) != set(QUAST_FIELDS.values()):
        raise ValueError('Missing QUAST metrics: '+str(set(QUAST_FIELDS.values()) - set(result)))
    return result


def fastq_records(path):
    opener = gzip.open if str(path).endswith('.gz') else open
    with opener(path,'rt',encoding='ascii') as file:
        while True:
            h = file.readline()
            if not h:
                return
            s,p,q = file.readline(),file.readline(),file.readline()
            if not (s and p and q and h.startswith('@') and p.startswith('+')):
                raise ValueError('Invalid/truncated FASTQ')
            seq, qual = s.rstrip('\r\n').upper(),q.rstrip('\r\n')
            if len(seq) != len(qual):
                raise ValueError('FASTQ seq/quality mismatch')
            name = h[1:].split()[0].removesuffix('/1').removesuffix('/2')
            yield name, seq, qual
