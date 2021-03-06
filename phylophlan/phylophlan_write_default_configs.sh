#!/bin/bash


# This script assumes to be executed by the setup.py script

outd='.'

if [ $# -eq 1 ]; then
    outd=$1
fi;

if [ ! -d $outd ]; then
    mkdir -p $outd
fi;

# supermatrix_nt.cfg
python phylophlan/phylophlan_write_config_file.py -o $outd/supermatrix_nt.cfg \
    -d n \
    --db_dna makeblastdb \
    --map_dna blastn \
    --msa mafft \
    --trim trimal \
    --tree1 fasttree \
    --tree2 raxml \
    --overwrite \
    --verbose

# supertree_nt.cfg
python phylophlan/phylophlan_write_config_file.py -o $outd/supertree_nt.cfg \
    -d n \
    --db_dna makeblastdb \
    --map_dna blastn \
    --msa mafft \
    --trim trimal \
    --gene_tree1 fasttree \
    --gene_tree2 raxml \
    --tree1 astral \
    --overwrite \
    --verbose

# supermatrix_aa.cfg
python phylophlan/phylophlan_write_config_file.py -o $outd/supermatrix_aa.cfg \
    -d a \
    --db_aa diamond \
    --map_dna diamond \
    --map_aa diamond \
    --msa mafft \
    --trim trimal \
    --tree1 fasttree \
    --tree2 raxml \
    --overwrite \
    --verbose

# supertree_aa.cfg
python phylophlan/phylophlan_write_config_file.py -o $outd/supertree_aa.cfg \
    -d a \
    --db_aa diamond \
    --map_dna diamond \
    --map_aa diamond \
    --msa mafft \
    --trim trimal \
    --gene_tree1 fasttree \
    --gene_tree2 raxml \
    --tree1 astral \
    --overwrite \
    --verbose

exit 0;
