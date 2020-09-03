#! /usr/bin/env python
"""
Do gather matches on contigs, and save to JSON
script from charcoal c7fd192
"""
import sys
import argparse
import os.path
import json

import screed

import sourmash
from sourmash.lca.command_index import load_taxonomy_assignments
from sourmash.lca import LCA_Database

from .lineage_db import LineageDB
from .version import version
from thumper.charcoal_utils import (gather_at_rank, get_ident, ContigSearchInfo, search_containment_at_rank)


def main(args):
    "Main entry point for scripting. Use cmdline for command line entry."
    genomebase = os.path.basename(args.genome)
    match_rank = 'genus'

    # load taxonomy CSV
    tax_assign, _ = load_taxonomy_assignments(args.lineages_csv,
                                              start_column=2)
    print(f'loaded {len(tax_assign)} tax assignments.')

    # load the genome signature
    genome_sig = sourmash.load_one_signature(args.genome_sig, select_moltype=args.alphabet, ksize=args.ksize)

    # load all of the matches from search --containment in the database
    with open(args.matches_sig, 'rt') as fp:
        try:
            siglist = list(sourmash.load_signatures(fp, do_raise=True,
                                                    quiet=False))
        except sourmash.exceptions.SourmashError:
            siglist = []
    print(f"loaded {len(siglist)} matches from '{args.matches_sig}'")

    # Hack for examining members of our search database: remove exact matches.
    new_siglist = []
    for ss in siglist:
        if genome_sig.similarity(ss) == 1.0:
            print(f'removing an identical match: {ss.name()}')
        else:
            new_siglist.append(ss)
    siglist = new_siglist

    # if, after removing exact match(es), there is nothing left, quit.
    # (but write an empty JSON file so that snakemake workflows don't
    # complain.)
    if not siglist:
        print('no non-identical matches for this genome, exiting.')
        contigs_tax = {}
        with open(args.json_out, 'wt') as fp:
            fp.write(json.dumps(contigs_tax))
        return 0

    # construct a template minhash object that we can use to create new 'uns
    empty_mh = siglist[0].minhash.copy_and_clear()
    ksize = empty_mh.ksize
    scaled = empty_mh.scaled
    moltype = empty_mh.moltype

    # create empty LCA database to populate...
    lca_db = LCA_Database(ksize=ksize, scaled=scaled, moltype=moltype)
    lin_db = LineageDB()

    # ...with specific matches.
    for ss in siglist:
        ident = get_ident(ss)
        lineage = tax_assign[ident]

        lca_db.insert(ss, ident=ident)
        lin_db.insert(ident, lineage)

    print(f'loaded {len(siglist)} signatures & created LCA Database')

    print('')
    print(f'reading contigs from {genomebase}')

    screed_iter = screed.open(args.genome)
    contigs_tax = {}
    for n, record in enumerate(screed_iter):
        # look at each contig individually
        mh = empty_mh.copy_and_clear()
        mh.add_sequence(record.sequence, force=True)
        # collect all the gather results at genus level, together w/counts;
        # here, results is a list of (lineage, count) tuples.
        # ntp: results is now (lineage,count, lin_mh, query_contained)
        results,rank_results = search_containment_at_rank(mh, lca_db, lin_db, match_rank)
        #results = gather_at_rank(mh, lca_db, lin_db, match_rank)

        # now summarize this up the chain
        #rank_summary = {}
        #if results:
        #    query_sig = sourmash.SourmashSignature(mh)
        #    for rank in sourmash.lca.taxlist():
        #        rank_summary[rank] = summarize_at_rank(results, query_sig, rank)
        #        if rank == match_rank:
        #            break

        ## WORKING HERE..now do something with these summaries
        #import pdb;pdb.set_trace()
        # store together with size of sequence.
        # note, don't want to store the minhashes here/write them out. Summarize first
        #info = ContigSearchInfo(len(record.sequence), len(mh), results, rank_results)
        info = ContigSearchInfo(len(record.sequence), len(mh), [], rank_results)
        contigs_tax[record.name] = info

    print(f"Processed {len(contigs_tax)} contigs.")

    # save!
    with open(args.json_out, 'wt') as fp:
        fp.write(json.dumps(contigs_tax))

    # write contig-level csv here instead/too?

    return 0


def cmdline(sys_args):
    "Command line entry point w/argparse action."
    p = argparse.ArgumentParser(sys_args)
    p.add_argument('--genome', help='genome file', required=True)
    p.add_argument('--genome-sig', help='genome sig', required=True)
    p.add_argument('--matches-sig', help='all relevant matches', required=True)
    p.add_argument('--lineages-csv', help='lineage spreadsheet', required=True)
    p.add_argument('--alphabet', help='alphabet', required=True)
    p.add_argument('--ksize', help='ksize', required=True)

    p.add_argument('--force', help='continue past survivable errors',
                   action='store_true')

    p.add_argument('--json-out',
                   help='JSON-format output file of all tax results',
                   required=True)
    args = p.parse_args()

    return main(args)


# execute this, when run with `python -m`.
if __name__ == '__main__':
    returncode = cmdline(sys.argv[1:])
    sys.exit(returncode)
