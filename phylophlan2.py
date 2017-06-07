#!/usr/bin/env python3


__author__ = 'Nicola Segata (nsegata@hsph.harvard.edu), Francesco Asnicar (f.asnicar@unitn.it)'
__version__ = '0.04'
__date__ = '15 May 2017'


import os
import sys
import glob
import shutil
import argparse as ap
import configparser as cp
import subprocess as sb
import multiprocessing as mp
from Bio import SeqIO # Biopython (v 1.69) require NumPy (v 1.12.1)
from Bio.Seq import Seq
from Bio.SeqRecord import SeqRecord
from Bio import AlignIO
from Bio.Align import MultipleSeqAlignment
from collections import Counter
import bz2
import math
import re
import hashlib
import time
import operator
import functools
import pickle
from itertools import combinations


CONFIG_SECTIONS_MANDATORY = [['map_dna', 'map_aa'], ['msa'], ['tree1']]
CONFIG_SECTIONS_ALL = ['map_dna', 'map_aa', 'msa', 'trim', 'gene_tree1', 'gene_tree2', 'tree1', 'tree2']
CONFIG_OPTIONS_MANDATORY = [['program_name', 'program_name_parallel'], ['command_line']]
CONFIG_OPTIONS_ALL = ['program_name', 'program_name_parallel', 'params', 'threads', 'input', 'database', 'output_path', 'output', 'version', 'command_line']
INPUT_FOLDER = 'input/'
DATA_FOLDER = 'data/'
DATABASES_FOLDER = 'databases/'
SUBMAT_FOLDER = 'substitution_matrices/'
CONFIG_FOLDER = 'configs/'
OUTPUT_FOLDER = 'output/'
TRIM_CHOICES = ['gappy', 'not_variant', 'greedy']
SUBSAMPLE_CHOICES = ['phylophlan', 'onehundred', 'fifty']
SCORING_FUNCTION_CHOICES = ['trident', 'muscle']
GENOME_EXTENSION = '.fna'
PROTEOME_EXTENSION = '.faa'


def info(s, init_new_line=False, exit=False, exit_value=0):
    if init_new_line:
        sys.stdout.write('\n')

    sys.stdout.write('{}'.format(s))
    sys.stdout.flush()

    if exit:
        sys.exit(exit_value)


def error(s, init_new_line=False, exit=False, exit_value=1):
    if init_new_line:
        sys.stderr.write('\n')

    sys.stderr.write('[e] {}\n'.format(s))
    sys.stderr.flush()

    if exit:
        sys.exit(exit_value)


def read_params():
    p = ap.ArgumentParser(description="")

    group = p.add_mutually_exclusive_group()
    group.add_argument('-i', '--integrate', metavar='PROJECT_NAME', type=str, default=None, help="Integrate user genomes into the PhyloPhlAn tree")
    group.add_argument('-u', '--user_tree', metavar='PROJECT_NAME', type=str, default=None, help="Build a phylogenetic tree using only genomes provided by the user")
    group.add_argument('-c', '--clean', metavar='PROJECT_NAME', type=str, default=None, help="Clean the final and partial data produced for the specified project")

    p.add_argument('-d', '--database', type=str, default=None, help="The name of the database to use")
    p.add_argument('-f', '--config_file', type=str, default=None, help="The configuration file to load")
    p.add_argument('-s', '--submat', type=str, default=None, help="Specify the substitution matrix to use")

    group = p.add_mutually_exclusive_group()
    group.add_argument('--strain', action='store_true', default=False, help="")
    group.add_argument('--species', action='store_true', default=False, help="")
    group.add_argument('--genus', action='store_true', default=False, help="")
    group.add_argument('--family', action='store_true', default=False, help="")
    group.add_argument('--order', action='store_true', default=False, help="")
    group.add_argument('--classs', action='store_true', default=False, help="")
    group.add_argument('--phylum', action='store_true', default=False, help="")
    group.add_argument('--tol', action='store_true', default=False, help="")
    group.add_argument('--meta', action='store_true', default=False, help="")

    group = p.add_argument_group(title="Folders", description="Parameters for setting the folders location")
    group.add_argument('--input_folder', type=str, default=INPUT_FOLDER, help="Path to the folder containing the folder with the input data, default input/")
    group.add_argument('--data_folder', type=str, default=DATA_FOLDER, help="Path to the folder where to store the intermediate files, default data/")
    group.add_argument('--databases_folder', type=str, default=DATABASES_FOLDER, help="Path to the folder where to store the intermediate files, default databases/")
    group.add_argument('--submat_folder', type=str, default=SUBMAT_FOLDER, help="Path to the folder containing the substition matrices to use to compute the column score for the subsampling step, default substition_matrices/")
    group.add_argument('--output_folder', type=str, default=OUTPUT_FOLDER, help="Path to the output folder where to save the results, default output/")

    p.add_argument('--clean_all', action='store_true', default=False, help="Remove all instalation and database files that are automatically generated at the first run of the pipeline")
    p.add_argument('--database_list', action='store_true', default=False, help="If specified lists the available databases that can be specified with the -d (or --database) option")
    p.add_argument('--submat_list', action='store_true', default=False, help="If specified lists the available substitution matrices that can be specified with the -s (or --submat) option")
    p.add_argument('--nproc', type=int, default=1, help="The number of CPUs to use, default 1")
    p.add_argument('--min_num_proteins', type=int, default=100, help="Proteomes (.faa) with less than this number of proteins will be discarded, default is 100")
    p.add_argument('--min_len_protein', type=int, default=50, help="Proteins in proteomes (.faa) shorter than this value will be discarded, default is 50\n")
    p.add_argument('--min_num_markers', type=int, default=0, help="Inputs that map less than this number of markers will be discarded, default is 0, i.e., no input will be discarded")
    p.add_argument('--trim', default=None, choices=TRIM_CHOICES, help="Specify which type of trimming to perform, default None. 'gappy' will use what specified in the 'trim' section of the configuration file (suggested, trimal --gappyout) to remove gappy colums; 'not_variant' will remove columns that have at least one amino acid appearing above a certain threshold (see --not_variant_threshold); 'greedy' performs both 'gappy' and 'not_variant'")
    p.add_argument('--not_variant_threshold', type=float, default=0.95, help="The value used to consider a column not variant when '--trim not_variant' is specified, default 0.95")
    p.add_argument('--subsample', default=None, choices=SUBSAMPLE_CHOICES, help="Specify which function to use to compute the number of positions to retain from single marker MSAs for the concatenated MSA, default None. 'phylophlan' compute the number of position for each marker as in PhyloPhlAn (almost!) (works only when --database phylophlan); 'onehundred' return the top 100 posisitons; 'fifty' return the top 50 positions; default None, the complete alignment will be used")
    p.add_argument('--scoring_function', default=None, choices=SCORING_FUNCTION_CHOICES, help="Specify which scoring function to use to evaluate columns in the MSA results")
    p.add_argument('--sort', action='store_true', default=False, help="If specified the markers will be ordered")
    p.add_argument('--remove_fragmentary_entries', action='store_true', default=False, help="If specified the MSAs will be checked and cleaned from fragmentary entries. See --fragmentary_threshold for the threshold values above which an entry will be considered fragmentary")
    p.add_argument('--fragmentary_threshold', type=float, default=0.85, help="The fraction of gaps in a MSA to be considered fragmentery and hence discarded, default 0.85")

    group = p.add_argument_group(title="Filename extensions", description="Parameters for setting the extensions of the input files")
    group.add_argument('--genome_extension', type=str, default=GENOME_EXTENSION, help="Set the extension for the genomes in your inputs, default .fna")
    group.add_argument('--proteome_extension', type=str, default=PROTEOME_EXTENSION, help="Set the extension for the proteomes in your inputs, default .faa")

    p.add_argument('--verbose', action='store_true', default=False, help="Makes PhyloPhlAn2 verbose")
    p.add_argument('-v', '--version', action='store_true', default=False, help="Prints the current PhyloPhlAn2 version")

    return p.parse_args()


def read_configs(config_file, verbose=False):
    configs = {}
    config = cp.ConfigParser()
    config.read(config_file)

    if verbose:
        info('Reading configuration file {}\n'.format(config_file))

    for sections in CONFIG_SECTIONS_MANDATORY:
        for section in sections:
            if section in config.sections(): # "DEFAULT" section not included!
                configs[section] = {}

                for option in CONFIG_OPTIONS_ALL:
                    if option in config[section]:
                        configs[section][option] = config[section][option]
                    else:
                        configs[section][option] = ''
            else:
                configs[section] = ''

    return configs


def check_args(args, verbose):
    if not args.databases_folder.endswith('/'):
        args.databases_folder += '/'

    if not args.submat_folder.endswith('/'):
        args.submat_folder += '/'

    if args.clean_all:
        check_and_create_folder(args.databases_folder, exit=True, verbose=verbose)
        return None
    elif args.version:
        info('PhyloPhlAn2 version {} ({})\n'.format(__version__, __date__), exit=True)
    elif args.database_list:
        database_list(args.databases_folder, exit=True)
    elif args.submat_list:
        submat_list(args.submat_folder, exit=True)
    elif (not args.integrate) and (not args.user_tree) and (not args.clean):
        error('either -i (--integrate), or -u (--user_tree), or -c (--clean) must be specified', exit=True)
    elif not args.database:
        error('-d (or --database) must be specified')
        database_list(args.databases_folder, exit=True)
    elif (not os.path.isdir(args.databases_folder+args.database)) and (not os.path.isfile(args.databases_folder+args.database+'.faa')) and (not os.path.isfile(args.databases_folder+args.database+'.faa.bz2')):
        error('database {} not found in {}'.format(args.database, args.databases_folder))
        database_list(args.databases_folder, exit=True)

    if args.integrate:
        project_name = args.integrate
    elif args.user_tree:
        project_name = args.user_tree
    elif args.clean:
        project_name = args.clean

    args.data_folder += project_name+'_'+args.database
    args.output_folder += project_name+'_'+args.database

    if not args.data_folder.endswith('/'):
        args.data_folder += '/'

    if not args.output_folder.endswith('/'):
        args.output_folder += '/'

    if args.clean:
        check_and_create_folder(args.data_folder, exit=True, verbose=verbose)
        check_and_create_folder(args.output_folder, exit=True, verbose=verbose)
        return None

    args.input_folder += project_name

    if not args.input_folder.endswith('/'):
        args.input_folder += '/'

    check_and_create_folder(args.input_folder, exit=True, verbose=verbose)
    check_and_create_folder(args.data_folder, create=True, exit=True, verbose=verbose)
    check_and_create_folder(args.databases_folder, exit=True, verbose=verbose)
    check_and_create_folder(args.output_folder, create=True, exit=True, verbose=verbose)

    if not args.genome_extension.startswith('.'):
        args.genome_extension = '.'+args.genome_extension

    if args.genome_extension.endswith('.'):
        args.genome_extension = args.genome_extension[:-1]

    if not args.proteome_extension.startswith('.'):
        args.proteome_extension = '.'+args.proteome_extension

    if args.proteome_extension.endswith('.'):
        args.proteome_extension = args.proteome_extension[:-1]

    if args.subsample:
        if (args.database != 'phylophlan') and (args.subsample == 'phylophlan'):
            error("scoring function 'phylophlan' is compatible only with 'phylophlan' database", exit=True)

    if args.database == 'phylophlan':
        args.sort = True

        if verbose:
            info('Setting args.sort=True because args.database=phylophlan')

    if args.strain: # params for strain-level phylogenies
        print('\n>  ARGS.STRAIN  <')
        args.config_file = None
        args.trim = 'greedy'
        args.not_variant_threshold = 0.99
        args.subsample = None
        args.submat_folder = SUBMAT_FOLDER
        args.submat = None
        print('{}\n'.format(args))
    elif args.species: # params for species-level phylogenies
        print('\n>  ARGS.SPECIES  <')
        args.submat = None
        args.config_file = None
        print('{}\n'.format(args))
    elif args.genus: # params for genus-level phylogenies
        print('\n>  ARGS.GENUS  <')
        args.submat = None
        args.config_file = None
        print('{}\n'.format(args))
    elif args.family: # params for family-level phylogenies
        print('\n>  ARGS.FAMILY  <')
        args.submat = None
        args.config_file = None
        print('{}\n'.format(args))
    elif args.order: # params for order-level phylogenies
        print('\n>  ARGS.ORDER  <')
        args.submat = None
        args.config_file = None
        print('{}\n'.format(args))
    elif args.classs: # params for class-level phylogenies
        print('\n>  ARGS.CLASS  <')
        args.submat = None
        args.config_file = None
        print('{}\n'.format(args))
    elif args.phylum: # params for phylum-level phylogenies
        print('\n>  ARGS.PHYLUM  <')
        args.submat = None
        args.config_file = None
        print('{}\n'.format(args))
    elif args.tol: # params for tree-of-life phylogenies
        print('\n>  ARGS.TOL  <')
        args.config_file = None
        args.trim = 'greedy'
        args.not_variant_threshold = 0.93
        args.subsample = 'fifty'
        args.submat_folder = SUBMAT_FOLDER
        args.submat = 'vtml240'

        if args.database == 'phylophlan':
            args.subsample = 'phylophlan'

        print('{}\n'.format(args))
    elif args.meta: # params for phylogenetic placement of metagenomic contigs
        print('\n>  ARGS.META  <')
        args.submat = None
        args.config_file = None
        print('{}\n'.format(print))
    else:
        print('\n>  CUSTOM  <')
        print('{}\n'.format(args))

    if not args.config_file:
        error('-f (or --config_file) must be specified')
        config_list(CONFIG_FOLDER, exit=True)
    elif not os.path.isfile(args.config_file):
        error('configuration file "{}" not found'.format(args.config_file))
        config_list(CONFIG_FOLDER, exit=True)
    elif not args.submat:
        error('-s (or --submat) must be specified')
        submat_list(args.submat_folder, exit=True)
    elif not os.path.isfile(args.submat_folder+args.submat+'.pkl'):
        error('substitution matrix "{}" not found in "{}"'.format(args.submat, args.submat_folder))
        submat_list(args.submat_folder, exit=True)

    return project_name


def check_configs(configs, verbose=False):
    for sections in CONFIG_SECTIONS_MANDATORY:
        mandatory_sections = False

        for section in sections:
            if verbose:
                info('Checking "{}" section in configuration file\n'.format(section))

            if section in configs:
                mandatory_sections = True
                break

        if not mandatory_sections:
            error('could not find "{}" section in configuration file'.format(section), exit=True)

        for options in CONFIG_OPTIONS_MANDATORY:
            mandatory_options = False

            for option in options:
                if (option in configs[section]) and configs[section][option]:
                    mandatory_options = True
                    break

            if not mandatory_options:
                error('could not find "{}" mandatory option in section "{}" in configuration file'.format(option, section), exit=True)

    for section, options in configs.items():
        mandatory_options = None
        actual_options = []

        for option in options:
            if option in ['command_line']:
                mandatory_options = [a.strip() for a in configs[section][option].split('#') if a.strip()]
            else:
                actual_options.append(option)

        if mandatory_options and actual_options:
            for option in mandatory_options:
                if option not in actual_options:
                    error('option {} not defined in section {} in your configuration file'.format(option, section), exit=True)
        else:
            error('wrongly formatted configuration file?', exit=True)


def check_and_create_folder(folder, create=False, exit=False, verbose=False):
    if not os.path.isdir(folder):
        if create:
            if verbose:
                info('Creating folder {}\n'.format(folder))

            os.mkdir(folder, mode=0o775)
            return True
        else:
            error('{} folder does not exists'.format(folder), exit=exit)
            return False

    return True


def check_dependencies(configs, nproc, verbose=False):
    for prog in [compose_command(configs[params], check=True, nproc=nproc) for params in configs]:
        try:
            if verbose:
                info('Checking {}\n'.format(' '.join(prog)))

            # sb.run(prog, stdout=sb.DEVNULL, stderr=sb.DEVNULL, check=True)
            sb.check_call(prog, stdout=sb.DEVNULL, stderr=sb.DEVNULL)
        except sb.CalledProcessError as cpe:
            error('{}'.format(cpe), exit=True)
        except:
            error('{} not installed or not present in system path'.format(' '.join(prog)), exit=True)


def database_list(databases_folder, exit=False):
    info('Available databases in "{}":\n    {}\n'.format(databases_folder, '\n    '.join(set([a.replace('.faa', '').replace('.bz2', '').replace('.udb', '') for a in os.listdir(databases_folder)]))), exit=exit)


def submat_list(submat_folder, exit=False):
    info('Available substitution matrices in "{}":\n    {}\n'.format(submat_folder, '\n    '.join(set([a.replace(submat_folder, '').replace('.pkl', '') for a in glob.iglob(submat_folder+'*.pkl')]))), exit=exit)


def config_list(config_folder, exit=False):
    info('Available configuration files in "{}":\n    {}\n'.format(config_folder, '\n    '.join(glob.iglob(config_folder+'*.cfg'))), exit=exit)


def compose_command(params, check=False, input_file=None, database=None, output_path=None, output_file=None, nproc=1):
    command_line = params['command_line'].replace('#program_name#', params['program_name'])
    program_name = params['program_name']

    if (nproc > 1) and params['program_name_parallel']:
        command_line = command_line.replace('#program_name_parallel#', params['program_name_parallel'])
        program_name = params['program_name_parallel']

    if check:
        command_line = program_name

        if params['version']:
            command_line = '{} {}'.format(program_name, params['version'])
    else:
        if params['params']:
            command_line = command_line.replace('#params#', params['params'])

        if params['threads']:
            command_line = command_line.replace('#threads#', '{} {}'.format(params['threads'], nproc))

        if output_path and params['output_path']:
            command_line = command_line.replace('#output_path#', '{} {}'.format(params['output_path'], output_path))

        if input_file:
            inp = input_file

            if params['input']:
                inp = '{} {}'.format(params['input'], input_file)

            command_line = command_line.replace('#input#', inp)

        if database and params['database']:
            command_line = command_line.replace('#database#', '{} {}'.format(params['database'], database))

        if output_file:
            out = output_file

            if params['output']:
                out = '{} {}'.format(params['output'], output_file)

            command_line = command_line.replace('#output#', out)

    # find if there are string params sourrunded with " and make thme as one string
    quotes = [j for j, e in enumerate(command_line) if e == '"']

    for s, e in zip(quotes[0::2], quotes[1::2]):
        command_line = command_line.replace(command_line[s+1:e], command_line[s+1:e].replace(' ', '#'))

    return [str(a).replace('#', ' ') for a in re.sub(' +', ' ', command_line.replace('"', '')).split(' ') if a]


def init_database(database, databases_folder, params, key_dna, key_aa, verbose=False):
    db_fasta, db_dna, db_aa, markers = None, None, None, None

    if os.path.isfile(databases_folder+database+'.faa'): # assumed to be a fasta file containing the markers
        db_fasta = databases_folder+database+'.faa'
        db_dna = databases_folder+database+'.faa'
        db_aa = databases_folder+database+'.udb'
    elif os.path.isfile(databases_folder+database+'.faa.bz2'):
        db_fasta = databases_folder+database+'.faa'
        db_dna = databases_folder+database+'.faa'
        db_aa = databases_folder+database+'.udb'
        markers = [databases_folder+database+'.faa.bz2']
    elif os.path.isdir(databases_folder+database): # assumed to be a folder with a fasta file for each marker
        db_fasta = databases_folder+database+'/'+database+'.faa'
        db_dna = databases_folder+database+'/'+database+'.faa'
        db_aa = databases_folder+database+'/'+database+'.udb'
        markers = glob.iglob(databases_folder+database+'/*.faa*')
    else: # what's that??
        error('custom set of markers ({}, {}, or {}) not recognize'.format(databases_folder+database+'.faa', databases_folder+database+'.faa.bz2', databases_folder+database+'/'), exit=True)

    if db_aa and (not os.path.isfile(db_aa)):
        if key_aa in params:
            make_database(params[key_aa], db_fasta, markers, db_aa, key_aa, verbose)
        else:
            error('cannot create database {}, section {} not present in configurations'.format(db_aa, key_aa), exit=True)
    elif verbose:
        info('{} database {} already present\n'.format(key_aa, db_aa))

    return (db_dna, db_aa)


def make_database(command, fasta, markers, db, label, verbose=False):
    if fasta and (not os.path.isfile(fasta)):
        with open(fasta, 'w') as f:
            for i in markers:
                g = bz2.open(i, 'rt') if i.endswith('.bz2') else open(i)
                f.write(g.read())
                g.close()
    elif verbose:
        info('File {} already present\n'.format(fasta))

    try:
        info('Generating {} indexed database {}\n'.format(label, db))
        cmd = compose_command(command, input_file=fasta, output_file=db)
        # sb.run(cmd, stdout=sb.DEVNULL, stderr=sb.DEVNULL, check=True))
        sb.check_call(cmd, stdout=sb.DEVNULL, stderr=sb.DEVNULL)
        info('Generated {} {}\n'.format(label, db))
    except sb.CalledProcessError as cpe:
        error('{}'.format(cpe), exit=True)
    except:
        error('{} not installed or not present in system path'.format(' '.join(cmd)), exit=True)


def clean_all(databases_folder, verbose=False):
    for f in glob.iglob(databases_folder+'*.udb'):
        if verbose:
            info('Removing {}\n'.format(f))

        os.remove(f)
        f_clean = f[:f.rfind('.')]

        if os.path.isfile(f_clean+'.faa') and os.path.isfile(f_clean+'.faa.bz2'):
            if verbose:
                info('Removing {}\n'.format(f_clean+'.faa'))

            os.remove(f_clean+'.faa')

    for database in os.listdir(databases_folder):
        for f in glob.iglob(databases_folder+database+'/'+database+'.faa'):
            if verbose:
                info('Removing {}\n'.format(f))

            os.remove(f)

        for f in glob.iglob(databases_folder+database+'/'+database+'.udb'):
            if verbose:
                info('Removing {}\n'.format(f))

            os.remove(f)

    sys.exit(0)


def clean_project(data_folder, output_folder, verbose=False):
    if os.path.exists(data_folder):
        if verbose:
            info('Removing folder {}\n'.format(data_folder))

        shutil.rmtree(data_folder)

    if os.path.exists(output_folder):
        if verbose:
            info('Removing folder {}\n'.format(output_folder))

        shutil.rmtree(output_folder)

    info('Folders {} and {} removed\n'.format(data_folder, output_folder))
    sys.exit(0)


def load_input_files(input_folder, tmp_folder, extension, verbose=False):
    inputs = {}

    if os.path.isdir(input_folder):
        info('Loading files from {}\n'.format(input_folder))
        files = glob.iglob(input_folder+'*'+extension+'*')

        for f in files:
            if f.endswith('.bz2'):
                if not os.path.isdir(tmp_folder):
                    if verbose:
                        info('Creating folder {}\n'.format(tmp_folder))

                    os.mkdir(tmp_folder)

                hashh = hashlib.sha1(f.encode(encoding='utf-8')).hexdigest()[:7]
                file_clean = f[f.rfind('/')+1:].replace(extension, '').replace('.bz2', '')+'_'+hashh+extension

                if not os.path.isfile(tmp_folder+file_clean):
                    with open(tmp_folder+file_clean, 'w') as g:
                        with bz2.open(f, 'rt') as h:
                            SeqIO.write(SeqIO.parse(h, "fasta"), g, "fasta")
                elif verbose:
                    info('File {} already decompressed\n'.format(tmp_folder+file_clean))

                inputs[file_clean] = tmp_folder
            elif f.endswith(extension):
                inputs[f[f.rfind('/')+1:]] = input_folder
            else:
                info('Input file {} not recognized\n'.format(f))

    elif verbose:
        info('Folder {} does not exists\n'.format(input_folder))

    return inputs


def initt(terminating_):
    # This places terminating in the global namespace of the worker subprocesses.
    # This allows the worker function to access `terminating` even though it is
    # not passed as an argument to the function.
    global terminating
    terminating = terminating_


def check_input_proteomes(inputs, min_num_proteins, min_len_protein, data_folder, nproc=1, verbose=False):
    good_inputs = []

    if os.path.isfile(data_folder+'checked_inputs.pkl'):
        info('Inputs already checked\n')

        if verbose:
            info('Loading checked inputs from {}\n'.format(data_folder+'checked_inputs.pkl'))

        with open(data_folder+'checked_inputs.pkl', 'rb') as f:
            good_inputs = pickle.load(f)
    else:
        info('Checking {} inputs\n'.format(len(inputs)))
        pool_error = False
        terminating = mp.Event()
        pool = mp.Pool(initializer=initt, initargs=(terminating, ), processes=nproc)
        chunksize = math.floor(len(inputs)/(nproc*2))

        try:
            good_inputs = pool.imap_unordered(check_input_proteomes_rec, ((inp_fol+inp, min_len_protein, min_num_proteins, verbose) for inp, inp_fol in inputs.items()), chunksize=chunksize if chunksize else 1)
            pool.close()
        except:
            pool.terminate()
            pool_error = True

        pool.join()

        if pool_error:
            error('check_input_proteomes crashed', exit=True)

        good_inputs = [a for a in good_inputs if a]

        with open(data_folder+'checked_inputs.pkl', 'wb') as f:
            pickle.dump(good_inputs, f, protocol=pickle.HIGHEST_PROTOCOL)

    return good_inputs


def check_input_proteomes_rec(x):
    if not terminating.is_set():
        try:
            inp, min_len_protein, min_num_proteins, verbose = x
            info('Checking {}\n'.format(inp))
            num_proteins = len([0 for seq_record in SeqIO.parse(inp, "fasta") if len(seq_record) >= min_len_protein])

            if num_proteins >= min_num_proteins:
                return inp
            elif verbose:
                info('{} discarded, not enough proteins ({}/{}) of at least {} AAs\n'.format(inp, num_proteins, min_num_proteins, min_len_protein))

            return None
        except:
            error('error while checking {}'.format(', '.join(x)))
            terminating.set()
            raise
    else:
        terminating.set()


def clean_input_proteomes(inputs, output_folder, nproc=1, verbose=False):
    commands = []

    if not os.path.isdir(output_folder):
        if verbose:
            info('Creating folder {}\n'.format(output_folder))

        os.mkdir(output_folder)
    elif verbose:
        info('Folder {} already exists\n'.format(output_folder))

    commands = [(inp, output_folder+inp[inp.rfind('/')+1:]) for inp in inputs if not os.path.isfile(output_folder+inp[inp.rfind('/')+1:])]

    if commands:
        info('Cleaning {} inputs\n'.format(len(commands)))
        pool_error = False
        terminating = mp.Event()
        pool = mp.Pool(initializer=initt, initargs=(terminating, ), processes=nproc)
        chunksize = math.floor(len(commands)/(nproc*2))

        try:
            pool.imap_unordered(clean_input_proteomes_rec, commands, chunksize=chunksize if chunksize else 1)
            pool.close()
        except:
            pool.terminate()
            pool_error = True

        pool.join()

        if pool_error:
            error('clean_input_proteomes crashed', exit=True)
    else:
        info('Inputs already cleaned\n')


def clean_input_proteomes_rec(x):
    if not terminating.is_set():
        try:
            t0 = time.time()
            inp, out = x
            inp_clean = inp[inp.rfind('/')+1:inp.rfind('.')]
            info('Cleaning {}\n'.format(inp))
            output = (SeqRecord(seq_record.seq, id='{}_{}'.format(inp_clean, counter), description='') for counter, seq_record in enumerate(SeqIO.parse(inp, "fasta")))

            with open(out, 'w') as f:
                SeqIO.write(output, f, "fasta")

            t1 = time.time()
            info('{} generated in {}s\n'.format(out, int(t1-t0)))
        except:
            error('error while cleaning {}'.format(', '.join(x)))
            terminating.set()
            raise
    else:
        terminating.set()


def gene_markers_identification(configs, key, inputs, output_folder, database_name, database, min_num_proteins, nproc=1, verbose=False):
    commands = []

    if not os.path.isdir(output_folder):
        if verbose:
            info('Creating folder {}\n'.format(output_folder))

        os.mkdir(output_folder)
    elif verbose:
        info('Folder {} already exists\n'.format(output_folder))

    for inp, inp_fol in inputs.items():
        out = output_folder+inp[:inp.rfind('.')]+'.b6o.bkp'

        if not os.path.isfile(out):
            commands.append((configs[key], inp_fol+inp, database, out, min_num_proteins))

    if commands:
        info('Mapping {} on {} inputs (key: {})\n'.format(database_name, len(commands), key))
        pool_error = False
        terminating = mp.Event()
        pool = mp.Pool(initializer=initt, initargs=(terminating, ), processes=nproc)
        chunksize = math.floor(len(commands)/(nproc*2))

        try:
            pool.imap_unordered(gene_markers_identification_rec, commands, chunksize=chunksize if chunksize else 1)
            pool.close()
        except:
            pool.terminate()
            pool_error = True

        pool.join()

        if pool_error:
            error('gene_markers_identification crashed', exit=True)
    else:
        info('{} markers already mapped (key: {})\n'.format(database_name, key))


def gene_markers_identification_rec(x):
    if not terminating.is_set():
        try:
            t0 = time.time()
            params, inp, db, out, min_num_proteins = x
            info('Mapping {}\n'.format(inp))
            cmd = compose_command(params, input_file=inp, database=db, output_file=out)
            # sb.run(cmd, stdout=sb.DEVNULL, stderr=sb.DEVNULL, check=True))
            sb.check_call(cmd, stdout=sb.DEVNULL, stderr=sb.DEVNULL)
            t1 = time.time()
            info('{} generated in {}s\n'.format(out, int(t1-t0)))
        except sb.CalledProcessError as cpe:
            error('{}'.format(cpe))
            terminating.set()
            raise
        except:
            error('cannot execute command {}'.format(' '.join(cmd)))
            terminating.set()
            raise
    else:
        terminating.set()


def gene_markers_selection(input_folder, function, min_num_proteins, nproc=1, verbose=False):
    commands = [(f, f[:-4], function, min_num_proteins) for f in  glob.iglob(input_folder+'*.b6o.bkp') if not os.path.isfile(f[:-4])]

    if commands:
        info('Selecting {} markers from {}\n'.format(len(commands), input_folder))
        pool_error = False
        terminating = mp.Event()
        pool = mp.Pool(initializer=initt, initargs=(terminating, ), processes=nproc)
        chunksize = math.floor(len(commands)/(nproc*2))

        try:
            pool.imap_unordered(gene_markers_selection_rec, commands, chunksize=chunksize if chunksize else 1)
            pool.close()
        except:
            pool.terminate()
            pool_error = True

        pool.join()

        if pool_error:
            error('gene_markers_selection crashed', exit=True)
    else:
        info('Markers already selected\n')


def gene_markers_selection_rec(x):
    if not terminating.is_set():
        try:
            t0 = time.time()
            inp, out, function, min_num_proteins = x
            info('Selecting {}\n'.format(inp))
            matches = function(inp)

            if len(matches) >= min_num_proteins: # there should be at least min_num_proteins mapped
                with open(out, 'w') as f:
                    f.write('{}\n'.format('\n'.join(['\t'.join(m) for m in matches])))

                t1 = time.time()
                info('{} generated in {}s\n'.format(out, int(t1-t0)))
            else:
                info('Not enough markers mapped ({}/{}) in {}\n'.format(len(matches), min_num_proteins, inp))
        except sb.CalledProcessError as cpe:
            error('{}'.format(cpe))
            terminating.set()
            raise
        except:
            error('cannot execute command {}'.format(' '.join(cmd)))
            terminating.set()
            raise
    else:
        terminating.set()


def best_hit(f):
    tab = (ll.strip().split('\t') for ll in open(f))
    best_matches = {}

    for entry in tab:
        c = entry[0].split(' ')[0]
        m = entry[1].split('_')[1]
        s = entry[6]
        e = entry[7]
        b = entry[-1]

        if (m in best_matches) and (float(b) > float(best_matches[m][-1])):
             best_matches[m] = [c, m, s, e, b]
        else:
             best_matches[m] = [c, m, s, e, b]

    return [v for _, v in best_matches.items()]


def largest_cluster(f):
    tab = (ll.strip().split('\t') for ll in open(f))
    clusters = {}
    largest_clusters = []

    for entry in tab:
        c = entry[0].split(' ')[0]
        m = entry[1].split('_')[1]

        if (c, m) in clusters:
            clusters[(c, m)].append(entry)
        else:
            clusters[(c, m)] = [entry]

    for (c, m), entries in clusters.items():
        cs = [int(s) for _, _, _, _, _, _, s, _, _, _, _, _ in entries]
        ce = [int(e) for _, _, _, _, _, _, _, e, _, _, _, _ in entries]
        ms = (int(s) for _, _, _, _, s, _, _, _, _, _, _, _ in entries)
        me = (int(e) for _, _, _, _, _, e, _, _, _, _, _, _ in entries)
        b = max((float(b) for _, _, _, _, _, _, _, _, _, _, _, b in entries))
        rev = False

        for s, e in zip(cs, ce):
            if s > e: # check if the contig positions are reverse
                rev = True
                break

        if not rev: # if contig position are forward
            for s, e in zip(ms, me):
                if s > e: # check if the marker positions are forward or reverse
                    rev = True
                    break

        largest_clusters.append([c, m, str(min(cs+ce)), str(max(cs+ce)), str(rev), str(b)])

    return largest_clusters


def gene_markers_extraction(inputs, input_folder, output_folder, extension, min_num_markers, nproc=1, verbose=False):
    commands = []

    if not os.path.isdir(output_folder):
        if verbose:
            info('Creating folder {}\n'.format(output_folder))

        os.mkdir(output_folder)
    elif verbose:
        info('Folder {} already exists\n'.format(output_folder))

    for f in glob.iglob(input_folder+'*.b6o'):
        f_clean = f[f.rfind('/')+1:].replace('.b6o', '')+extension
        src_file = inputs[f_clean]+f_clean
        out_file = output_folder+f_clean

        if os.path.isfile(src_file) and (not os.path.isfile(out_file)):
            commands.append((out_file, src_file, f, min_num_markers))

    if commands:
        info('Extracting markers from {} inputs\n'.format(len(commands)))
        pool_error = False
        terminating = mp.Event()
        pool = mp.Pool(initializer=initt, initargs=(terminating, ), processes=nproc)
        chunksize = math.floor(len(commands)/(nproc*2))

        try:
            pool.imap_unordered(gene_markers_extraction_rec, commands, chunksize=chunksize if chunksize else 1)
            pool.close()
        except:
            pool.terminate()
            pool_error = True

        pool.join()

        if pool_error:
            error('gene_markers_extraction crashed', exit=True)
    else:
        info('Markers already extracted\n')


def gene_markers_extraction_rec(x):
    if not terminating.is_set():
        try:
            t0 = time.time()
            out_file, src_file, b6o_file, min_num_markers = x
            out_file_seq = []
            contig2markers = {}
            marker2b6o = {}
            info('Extracting {}\n'.format(b6o_file))

            for l in open(b6o_file):
                row = l.strip().split('\t')
                contig = row[0]
                marker = row[1]
                start = int(row[2])
                end = int(row[3])
                rev = bool(row[4])

                if contig in contig2markers:
                    contig2markers[contig].append(marker)
                else:
                    contig2markers[contig] = [marker]

                if marker in marker2b6o:
                    error('{}'.format(marker))
                else:
                    marker2b6o[marker] = (start, end, rev)

            for seq_record in SeqIO.parse(src_file, "fasta"):
                if seq_record.id in contig2markers:
                    for marker in contig2markers[seq_record.id]:
                        s, e, rev = marker2b6o[marker]
                        idd = '{}_{}:'.format(seq_record.id, marker)

                        if rev:
                            idd += 'c'

                        idd += '{}-{}'.format(s, e)
                        out_file_seq.append(SeqRecord(seq_record.seq[s-1:e], id=idd, description=''))

            if out_file_seq and (len(out_file_seq) >= min_num_markers):
                with open(out_file, 'w') as f:
                    SeqIO.write(out_file_seq, f, 'fasta')

                t1 = time.time()
                info('{} generated in {}s\n'.format(out_file, int(t1-t0)))
            else:
                info('Not enough markers ({}/{}) found in {}\n'.format(len(out_file_seq), min_num_markers, b6o_file))
        except:
            error('error while extracting {}'.format(', '.join(x)))
            terminating.set()
            raise
    else:
        terminating.set()


def fake_proteome(input_folder, output_folder, in_extension, out_extension, nproc=1, verbose=False):
    commands = []

    if not os.path.isdir(output_folder):
        if verbose:
            info('Creating folder {}\n'.format(output_folder))

        os.mkdir(output_folder)
    elif verbose:
        info('Folder {} already exists\n'.format(output_folder))

    for f in glob.iglob(input_folder+'*'+in_extension):
        out = output_folder+f[f.rfind('/')+1:f.rfind('.')]+out_extension

        if not os.path.isfile(out):
            commands.append((f, out))

    if commands:
        info('Generated proteomes from {} genomes\n'.format(len(commands)))
        pool_error = False
        terminating = mp.Event()
        pool = mp.Pool(initializer=initt, initargs=(terminating, ), processes=nproc)
        chunksize = math.floor(len(commands)/(nproc*2))

        try:
            pool.imap_unordered(fake_proteome_rec, commands, chunksize=chunksize if chunksize else 1)
            pool.close()
        except:
            pool.terminate()
            pool_error = True

        pool.join()

        if pool_error:
            error('fake_proteomes crashed', exit=True)
    else:
        info('Fake proteomes already generated\n')


def fake_proteome_rec(x):
    if not terminating.is_set():
        try:
            t0 = time.time()
            inp, out = x
            proteome = []
            info('Generating {}\n'.format(inp))

            for record in SeqIO.parse(inp, 'fasta'):
                seq = record.seq
                s, e = record.id.split(':')[-1].split('-')
                rev = False

                if s.startswith('c'):
                    s = s[1:]
                    rev = True

                if rev:
                    seq = record.seq.reverse_complement()

                while (len(seq) % 3) != 0:
                    seq += Seq('N')

                proteome.append(SeqRecord(Seq.translate(seq), id=record.id, description=''))

            with open(out, 'w') as f:
                SeqIO.write(proteome, f, 'fasta')

            t1 = time.time()
            info('{} generated in {}s\n'.format(out, int(t1-t0)))
        except:
            error('error while generating {}'.format(', '.join(x)))
            terminating.set()
            raise
    else:
        terminating.set()


def inputs2markers(input_folder, extension, output_folder, verbose=False):
    markers2inputs = {}

    if not os.path.isdir(output_folder):
        if verbose:
            info('Creating folder {}\n'.format(output_folder))

        os.mkdir(output_folder)
    elif verbose:
        info('Folder {} already exists\n'.format(output_folder))

        for f in glob.iglob(output_folder+'*'+extension):
            info('Markers already extracted\n')
            break

        return

    for f in glob.iglob(input_folder+'*'+extension):
        inp = f[f.rfind('/')+1:f.rfind('.')]

        for seq_record in SeqIO.parse(f, "fasta"):
            marker = seq_record.id.split(':')[0].split('_')[-1]

            if marker in markers2inputs:
                markers2inputs[marker].append(SeqRecord(seq_record.seq, id=inp, description=''))
            else:
                markers2inputs[marker] = [SeqRecord(seq_record.seq, id=inp, description='')]

    for marker, sequences in markers2inputs.items():
        with open(output_folder+marker+extension, 'w') as f:
            SeqIO.write(sequences, f, 'fasta')


def integrate(inp_f, database, data_folder, nproc=1, verbose=False):
    commands, ret_ids = [], []

    if os.path.isfile(data_folder+'integrate_ids.pkl'):
        info('Integration already performed\n')

        if verbose:
            info('Loading integrated ids from {}\n'.format(data_folder+'integrate_ids.pkl'))

        with open(data_folder+'integrate_ids.pkl', 'rb') as f:
            ret_ids = pickle.load(f)
    else:
        if os.path.isdir(database):
            markers = glob.glob(database+'/*')
            folder = True
        elif os.path.isfile(database+'.faa'):
            mrk_db = database+'.faa'
            folder = False
        else:
            error("integrate() what's this {}??".format(database), exit=True)

        for mrk in glob.iglob(inp_f+'*'):
            marker = mrk[mrk.rfind('/')+1:mrk.rfind('.')]

            if folder:
                mrks = [m for m in markers if marker in m]

                if len(mrks) == 1:
                    mrk_db = mrks[0]
                    marker = None
                else:
                    error('ambiguous marker {} in [{}]'.format(marker, ', '.join(mrks)), exit=True)

            commands.append((mrk, mrk_db, marker))

        if commands:
            info('Integrating {} markers\n'.format(len(commands)))
            pool_error = False
            terminating = mp.Event()
            pool = mp.Pool(initializer=initt, initargs=(terminating, ), processes=nproc)
            chunksize = math.floor(len(commands)/(nproc*2))

            try:
                ret_ids = pool.imap_unordered(integrate_rec, commands, chunksize=chunksize if chunksize else 1)
                pool.close()
            except:
                pool.terminate()
                pool_error = True

            pool.join()

            if pool_error:
                error('integrate crashed', exit=True)

            ret_ids = set([a for sublist in ret_ids for a in sublist])

            with open(data_folder+'integrate_ids.pkl', 'wb') as f:
                pickle.dump(ret_ids, f, protocol=pickle.HIGHEST_PROTOCOL)
        else:
            info('No markers to integrate\n')

    return ret_ids


def integrate_rec(x):
    if not terminating.is_set():
        try:
            t0 = time.time()
            ret_ids = None
            mrk_in, mrk_db, marker = x
            info('Integrating {}\n'.format(mrk_in))

            with open(mrk_in, 'a') as f:
                if marker:
                    SeqIO.write((record for record in SeqIO.parse(mrk_db, "fasta") if marker in record.id), f, "fasta")
                    ret_ids = [record.id for record in SeqIO.parse(mrk_db, "fasta") if marker in record.id]
                else:
                    with open(mrk_db) as g:
                        f.write(g.read())

                    ret_ids = [record.id for record in SeqIO.parse(mrk_db, "fasta")]

            t1 = time.time()
            info('{} finished in {}s\n'.format(mrk_in, int(t1-t0)))

            if ret_ids:
                return set(ret_ids)
            else:
                print('\n\nNO ret_ids {}\n\n'.format(x))
        except:
            error('error while integrating {}'.format(mrk_in))
            print('\n\n{}\n\n'.format(x))
            terminating.set()
            raise
    else:
        terminating.set()


def msas(configs, key, input_folder, extension, output_folder, nproc=1, verbose=False):
    commands = []

    if not os.path.isdir(output_folder):
        if verbose:
            info('Creating folder {}\n'.format(output_folder))

        os.mkdir(output_folder)
    elif verbose:
        info('Folder {} already exists\n'.format(output_folder))

    for inp in glob.iglob(input_folder+'*'+extension):
        out = output_folder+inp[inp.rfind('/')+1:inp.rfind('.')]+'.aln'

        if not os.path.isfile(out):
            commands.append((configs[key], inp, out))

    if commands:
        info('Aligning {} markers (key: {})\n'.format(len(commands), key))
        pool_error = False
        terminating = mp.Event()
        pool = mp.Pool(initializer=initt, initargs=(terminating, ), processes=nproc)
        chunksize = math.floor(len(commands)/(nproc*2))

        try:
            pool.imap_unordered(msas_rec, commands, chunksize=chunksize if chunksize else 1)
            pool.close()
        except:
            pool.terminate()
            pool_error = True

        pool.join()

        if pool_error:
            error('msas crashed', exit=True)
    else:
        info('Markers already aligned (key: {})\n'.format(key))


def msas_rec(x):
    if not terminating.is_set():
        try:
            t0 = time.time()
            params, inp, out = x
            info('Aligning {}\n'.format(inp))
            cmd = compose_command(params, input_file=inp, output_file=out)
            # sb.run(cmd, stdout=sb.DEVNULL, stderr=sb.DEVNULL, check=True))
            sb.check_call(cmd, stdout=sb.DEVNULL, stderr=sb.DEVNULL)
            t1 = time.time()
            info('{} generated in {}s\n'.format(out, int(t1-t0)))
        except sb.CalledProcessError as cpe:
            error('{}'.format(cpe))
            terminating.set()
            raise
        except:
            error('error while aligning {}'.format(', '.join(x)))
            terminating.set()
            raise
    else:
        terminating.set()


def trim_gappy(configs, key, inputt, output_folder, nproc=1, verbose=False):
    commands = []

    if not os.path.isdir(output_folder):
        if verbose:
            info('Creating folder {}\n'.format(output_folder))

        os.mkdir(output_folder)
    elif verbose:
        info('Folder {} already exists\n'.format(output_folder))

    if os.path.isdir(inputt):
        for inp in glob.iglob(inputt+'*.aln'):
            out = output_folder+inp[inp.rfind('/')+1:]

            if not os.path.isfile(out):
                commands.append((configs[key], inp, out))
    elif os.path.isfile(inputt):
        out = inputt[:inputt.rfind('.')]+'.trim'+inputt[inputt.rfind('.'):]

        if not os.path.isfile(out):
            commands.append((configs[key], inputt, out))
    else:
        error('unrecognized input {} is not a folder nor a file'.format(inputt), exit=True)

    if commands:
        info('Trimming gappy form {} markers (key: {})\n'.format(len(commands), key))
        pool_error = False
        terminating = mp.Event()
        pool = mp.Pool(initializer=initt, initargs=(terminating, ), processes=nproc)
        chunksize = math.floor(len(commands)/(nproc*2))

        try:
            pool.imap_unordered(trim_gappy_rec, commands, chunksize=chunksize if chunksize else 1)
            pool.close()
        except:
            pool.terminate()
            pool_error = True

        pool.join()

        if pool_error:
            error('trim_gappy crashed', exit=True)
    else:
        info('Markers already trimmed (key: {})\n'.format(key))


def trim_gappy_rec(x):
    if not terminating.is_set():
        try:
            t0 = time.time()
            params, inp, out = x
            info('Trimming gappy {}\n'.format(inp))
            cmd = compose_command(params, input_file=inp, output_file=out)
            # sb.run(cmd, stdout=sb.DEVNULL, stderr=sb.DEVNULL, check=True))
            sb.check_call(cmd, stdout=sb.DEVNULL, stderr=sb.DEVNULL)
            t1 = time.time()
            info('{} generated in {}s\n'.format(out, int(t1-t0)))
        except sb.CalledProcessError as cpe:
            error('{}'.format(cpe))
            terminating.set()
            raise
        except:
            error('error while trimming {}'.format(', '.join(x)))
            terminating.set()
            raise
    else:
        terminating.set()


def trim_not_variant(inputt, output_folder, threshold=0.9, nproc=1, verbose=False):
    commands = []

    if not os.path.isdir(output_folder):
        if verbose:
            info('Creating folder {}\n'.format(output_folder))

        os.mkdir(output_folder)
    elif verbose:
        info('Folder {} already exists\n'.format(output_folder))

    if os.path.isdir(inputt):
        for inp in glob.iglob(inputt+'*.aln'):
            out = output_folder+inp[inp.rfind('/')+1:]

            if not os.path.isfile(out):
                commands.append((inp, out, threshold))
    elif os.path.isfile(inputt):
        out = inputt[:inputt.rfind('.')]+'.trim'+inputt[inputt.rfind('.'):]

        if not os.path.isfile(out):
            commands.append((inputt, out, threshold))
    else:
        error('unrecognized input {} is not a folder nor a file'.format(inputt), exit=True)

    if commands:
        info('Trimming not variant from {} markers\n'.format(len(commands)))
        pool_error = False
        terminating = mp.Event()
        pool = mp.Pool(initializer=initt, initargs=(terminating, ), processes=nproc)
        chunksize = math.floor(len(commands)/(nproc*2))

        try:
            pool.imap_unordered(trim_not_variant_rec, commands, chunksize=chunksize if chunksize else 1)
            pool.close()
        except:
            pool.terminate()
            pool_error = True

        pool.join()

        if pool_error:
            error('trim_not_variant crashed', exit=True)
    else:
        info('Markers already trimmed\n')


def trim_not_variant_rec(x):
    if not terminating.is_set():
        try:
            t0 = time.time()
            inp, out, thr = x
            info('Trimming not variant {}\n'.format(inp))
            inp_aln = AlignIO.read(inp, "fasta")
            nrows = len(inp_aln)
            cols_to_remove = []
            sub_aln = []

            for i in range(len(inp_aln[0])):
                for aa, fq in Counter(inp_aln[:, i]).items():
                    if (fq/nrows) >= thr:
                        cols_to_remove.append(i)
                        break

            for aln in inp_aln:
                seq = ''.join([c for i, c in enumerate(aln.seq) if i not in cols_to_remove])
                sub_aln.append(SeqRecord(Seq(seq), id=aln.id, description=''))

            with open(out, 'w') as f:
                AlignIO.write(MultipleSeqAlignment(sub_aln), f, "fasta")

            t1 = time.time()
            info('{} generated in {}s\n'.format(out, int(t1-t0)))
        except:
            error('error while trimming {}'.format(', '.join(x)))
            terminating.set()
            raise
    else:
        terminating.set()


def remove_fragmentary_entries(input_folder, output_folder, threshold, verbose=False):
    commands = []

    if not os.path.isdir(output_folder):
        if verbose:
            info('Creating folder {}\n'.format(output_folder))

        os.mkdir(output_folder)
    elif verbose:
        info('Folder {} already exists\n'.format(output_folder))

    for inp in glob.iglob(input_folder+'*.aln'):
        out = output_folder+inp[inp.rfind('/')+1:]

        if not os.path.isfile(out):
            commands.append((inp, out, threshold))

    if commands:
        info('Removing {} fragmentary entries\n'.format(len(commands)))
        pool_error = False
        terminating = mp.Event()
        pool = mp.Pool(initializer=initt, initargs=(terminating, ), processes=nproc)
        chunksize = math.floor(len(commands)/(nproc*2))

        try:
            pool.imap_unordered(remove_fragmentary_entries_rec, commands, chunksize=chunksize if chunksize else 1)
            pool.close()
        except:
            pool.terminate()
            pool_error = True

        pool.join()

        if pool_error:
            error('remove_fragmentary_entries crashed', exit=True)
    else:
        info('Fragmentary entries already removed\n')


def remove_fragmentary_entries_rec(x):
    if not terminating.is_set():
        try:
            t0 = time.time()
            inp, out, thr = x
            info('Fragmentary {}\n'.format(inp))
            inp_aln = AlignIO.read(inp, "fasta")
            out_aln = []

            for aln in inp_aln:
                if gap_cost(aln.seq) < thr:
                    out_aln.append(aln)

            with open(out, 'w') as f:
                AlignIO.write(MultipleSeqAlignment(out_aln), out, 'fasta')

            t1 = time.time()
            info('{} generated in {}s\n'.format(out, int(t1-t0)))
        except:
            error('error while removing fragmentary {}'.format(', '.join(x)))
            terminating.set()
            raise
    else:
        terminating.set()


def subsample(input_folder, output_folder, positions_function, scoring_function, submat, nproc=1, verbose=False):
    commands = []
    mat = {}

    if not os.path.isfile(submat):
        error('could not find substitution matrix {}'.format(submat), exit=True)
    else:
        with open(submat, 'rb') as f:
            mat = pickle.load(f)

        if verbose:
            info('substitution matrix {} loaded\n'.format(submat))

    if not os.path.isdir(output_folder):
        if verbose:
            info('Creating folder {}\n'.format(output_folder))

        os.mkdir(output_folder)
    elif verbose:
        info('Folder {} already exists\n'.format(output_folder))

    for inp in glob.iglob(input_folder+'*.aln'):
        out = output_folder+inp[inp.rfind('/')+1:]

        if not os.path.isfile(out):
            commands.append((inp, out, positions_function, scoring_function, mat))

    if commands:
        info('Subsampling {} markers\n'.format(len(commands)))
        pool_error = False
        terminating = mp.Event()
        pool = mp.Pool(initializer=initt, initargs=(terminating, ), processes=nproc)
        chunksize = math.floor(len(commands)/(nproc*2))

        try:
            pool.imap_unordered(subsample_rec, commands, chunksize=chunksize if chunksize else 1)
            pool.close()
        except:
            pool.terminate()
            pool_error = True

        pool.join()

        if pool_error:
            error('subsample crashed', exit=True)
    else:
        info('Markers already subsampled\n')


def subsample_rec(x):
    if not terminating.is_set():
        try:
            t0 = time.time()
            inp, out, npos_function, score_function, mat = x
            info('Subsampling {}\n'.format(inp))
            inp_aln = AlignIO.read(inp, "fasta")
            scores = []
            out_aln = []

            for i in range(len(inp_aln[0])):
                col = set(inp_aln[:, i].upper())

                if (len(col) == 1) or \
                   (len(col) == 2 and ("-" in col or "X" in col)) or \
                   (len(col) == 3 and "X" in col and "-" in col):
                    continue

                unknowns = col.count("-")
                unknowns += col.count("X")

                if unknowns > (len(col)*0.1):
                    continue

                scores.append((score_function(inp_aln[:, i], mat), i))

            try:
                marker = inp[inp.rfind('/')+1:inp.rfind('.')][1:]
                marker = int(marker)
            except:
                marker = None

            npos = npos_function(marker)
            best_npos = [p for _, p in sorted(scores)[-npos:]]

            for aln in inp_aln:
                seq = ''.join([c for i, c in enumerate(aln.seq) if i in best_npos])
                out_aln.append(SeqRecord(Seq(seq), id=aln.id, description=''))

            with open(out, 'w') as f:
                AlignIO.write(MultipleSeqAlignment(out_aln), out, 'fasta')

            t1 = time.time()
            info('{} generated in {}s\n'.format(out, int(t1-t0)))
        except:
            error('error while subsampling {}'.format(', '.join(x)))
            terminating.set()
            raise
    else:
        terminating.set()


def phylophlan(marker):
    # return max(int(max(int((400-marker)*30/400.0), 1)**2/30.0), 3) # ~4k AAs (original PhyloPhlAn formulae)
    return max(int(math.ceil(max(int(math.ceil((400-marker)*30/400.0)), 1)**2/30.0)), 3) # ~4.6k AAs


def onehundred(_):
    return 100


def fifty(_):
    return 50


def trident(seq, submat, alpha=1, beta=0.5, gamma=3):
    return (1-symbol_diversity(seq))**alpha * (1-stereochemical_diversity(seq, submat))**beta * (1-gap_cost(seq))**gamma


def muscle(seq, submat):
    combos = [submat[a, b] for a, b in combinations(seq.upper().replace('-', ''), 2)]
    retval = 0.0

    if len(combos):
        retval = sum(combos)/len(combos) # average score over pairs of letters in the column.

    return retval


def symbol_diversity(seq, log_base=21):
    """
    Sander C, Schneider R. Database of homology-derived protein structures and the structural meaning of sequence alignment. Proteins 1991;9:56 – 68.
    """
    sh = 0.0

    for aa, abs_freq in Counter(seq.upper()).items():
        rel_freq = abs_freq/len(seq)
        sh -= rel_freq*math.log(rel_freq)

    sh /= math.log(min(len(seq), log_base))
    return sh if (sh > 0.15) and (sh < 0.85) else 0.99


def stereochemical_diversity(seq, submat):
    """
    Valdar W. Scoring Residue Conservation. PROTEINS: Structure, Function, and Genetics 48:227–241 (2002)
    """
    set_seq = set(seq.upper())
    aa_avg = sum([normalized_submat_scores(aa, submat) for aa in set_seq])
    aa_avg /= len(set_seq)
    r = sum([abs(aa_avg-normalized_submat_scores(aa, submat)) for aa in set_seq])
    r /= len(set_seq)
    r /= math.sqrt(20*(max(submat.values())-min(submat.values()))**2)
    return r


def normalized_submat_scores(aa, submat):
    """
    Karlin S, Brocchieri L. Evolutionary conservation of RecA genes in relation to protein structure and function. J Bacteriol 1996;178: 1881–1894.
    """
    aas = ['A', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'K', 'L', 'M', 'N', 'P', 'Q', 'R', 'S', 'T', 'V', 'W', 'Y']
    aa = aa.upper()
    m = 0.0

    if (aa != '-') and (aa != 'X'):
        for bb in aas:
            try:
                m += submat[(aa, bb)]/math.sqrt(submat[(aa, aa)]*submat[(bb, bb)])
            except:
                print('aa:{}, bb:{}, submat: {}'.format(aa, bb, submat))
                print('\n{}\n'.format(sys.exc_info()))
                sys.exit()

    return m


def gap_cost(seq, norm=True):
    gaps = seq.count('-')

    if norm:
        gaps /= len(seq)

    return gaps


def concatenate(all_inputs, input_folder, output_file, sort=False, verbose=False):
    if os.path.isfile(output_file):
        info('Alignments already merged {}\n'.format(output_file))
        return

    info('Concatenating alignments\n')
    all_inputs = set(all_inputs)
    print('\nlen(all_inputs): {}'.format(len(all_inputs)))
    inputs2alingments = dict(((inp, SeqRecord(Seq(''), id='{}'.format(inp), description='')) for inp in all_inputs))
    print('len(inputs2alingments): {}\n'.format(len(inputs2alingments)))
    markers = glob.iglob(input_folder+'*')

    if sort:
        markers = sorted(markers)

    for a in markers:
        print('\nmarker: {}'.format(a))
        alignment_length = None

        for seq_record in SeqIO.parse(a, "fasta"):
            inputs2alingments[seq_record.id].seq += seq_record.seq

            if not alignment_length:
                alignment_length = len(seq_record.seq)
                print('alignment_length: {}'.format(alignment_length))

        current_inputs = set([seq_record.id for seq_record in SeqIO.parse(a, "fasta")])
        print('len(current_inputs): {}'.format(len(current_inputs)))
        print('len(all_inputs-current_inputs): {}\n'.format(len(all_inputs-current_inputs)))

        for inp in all_inputs-current_inputs:
            inputs2alingments[inp].seq += Seq('-'*alignment_length)

    with open(output_file, 'w') as f:
        SeqIO.write([v for _, v in inputs2alingments.items()], f, "fasta")

    info('Alignments concatenated {}\n'.format(output_file))


def build_gene_tree(configs, key, input_folder, output_folder, nproc=1, verbose=False):
    commands = []

    if not os.path.isdir(output_folder):
        if verbose:
            info('Creating folder {}\n'.format(output_folder))

        os.mkdir(output_folder)
    elif verbose:
        info('Folder {} already exists\n'.format(output_folder))

    for inp in glob.iglob(input_folder+'*'):
        out = output_folder+inp[inp.rfind('/')+1:inp.rfind('.')]+'.tre'

        if not os.path.isfile(out):
            commands.append((configs[key], inp, os.path.abspath(output_folder), out))

    if commands:
        info('Building {} gene trees\n'.format(len(commands)))
        pool_error = False
        terminating = mp.Event()
        pool = mp.Pool(initializer=initt, initargs=(terminating, ), processes=nproc)
        chunksize = math.floor(len(commands)/(nproc*2))

        try:
            pool.imap_unordered(build_gene_tree_rec, commands, chunksize=chunksize if chunksize else 1)
            pool.close()
        except:
            pool.terminate()
            pool_error = True

        pool.join()

        if pool_error:
            error('build_gene_tree crashed', exit=True)
    else:
        info('Gene trees already built\n')


def build_gene_tree_rec(x):
    if not terminating.is_set():
        try:
            t0 = time.time()
            params, inp, abs_wf, out = x
            info('Building gene tree {}\n'.format(inp))
            cmd = compose_command(params, input_file=inp,  output_path=abs_wf, output_file=out)
            # sb.run(cmd, stdout=sb.DEVNULL, stderr=sb.DEVNULL, check=True))
            sb.check_call(cmd, stdout=sb.DEVNULL, stderr=sb.DEVNULL)
            t1 = time.time()
            info('{} generated in {}s\n'.format(out, int(t1-t0)))
        except sb.CalledProcessError as cpe:
            error('{}'.format(cpe))
            terminating.set()
            raise
        except:
            error('error while building gene tree {}'.format(', '.join(x)))
            terminating.set()
            raise
    else:
        terminating.set()


def refine_gene_tree(configs, key, input_alns, input_trees, output_folder, nproc=1, verbose=False):
    commands = []

    if not os.path.isdir(output_folder):
        if verbose:
            info('Creating folder {}\n'.format(output_folder))

        os.mkdir(output_folder)
    elif verbose:
        info('Folder {} already exists\n'.format(output_folder))

    for inp in glob.iglob(input_alns+'*'):
        starting_tree = input_trees+inp[inp.rfind('/')+1:inp.rfind('.')]+'.tre'
        out = output_folder+inp[inp.rfind('/')+1:inp.rfind('.')]+'.tre'

        if os.path.isfile(starting_tree):
            if not os.path.isfile(out):
                commands.append((configs[key], inp, starting_tree, os.path.abspath(output_folder), out))
        else:
            error('starting tree {} not found in {}, derived from {}'.format(starting_tree, input_trees, inp))

    if commands:
        info('Refining {} gene trees\n'.format(len(commands)))
        pool_error = False
        terminating = mp.Event()
        pool = mp.Pool(initializer=initt, initargs=(terminating, ), processes=nproc)
        chunksize = math.floor(len(commands)/(nproc*2))

        try:
            pool.imap_unordered(refine_gene_tree_rec, commands, chunksize=chunksize if chunksize else 1)
            pool.close()
        except:
            pool.terminate()
            pool_error = True

        pool.join()

        if pool_error:
            error('refine_gene_tree crashed', exit=True)
    else:
        info('Gene trees already refined\n')


def refine_gene_tree_rec(x):
    if not terminating.is_set():
        try:
            t0 = time.time()
            params, inp, st, abs_wf, out = x
            info('Refining gene tree {}\n'.format(inp))
            cmd = compose_command(params, input_file=inp, database=st, output_path=abs_wf, output_file=out)
            # sb.run(cmd, stdout=sb.DEVNULL, stderr=sb.DEVNULL, check=True))
            sb.check_call(cmd, stdout=sb.DEVNULL, stderr=sb.DEVNULL)
            t1 = time.time()
            info('{} generated in {}s\n'.format(out, int(t1-t0)))
        except sb.CalledProcessError as cpe:
            error('{}'.format(cpe))
            terminating.set()
            raise
        except:
            error('error while refining gene tree {}'.format(', '.join(x)))
            terminating.set()
            raise
    else:
        terminating.set()


def merging_gene_trees(trees_folder, output_file, verbose=False):
    if path.exists(output_file):
        info('Gene trees already merged {}\n'.format(output_folder))
        return

    info('Merging gene trees\n')

    with open(output_file, 'w') as f:
        for gtree in glob.iglob(trees_folder+"*"):
            if verbose:
                info('{} '.format(gtree))

            with open(gtree) as g:
                f.write(g.read())

    if verbose:
        info('\n'.format(gtree))


def build_phylogeny(configs, key, inputt, output_path, output_tree, nproc=1, verbose=False):
    if not os.path.isfile(output_tree):
        try:
            t0 = time.time()
            info('Building phylogeny {}\n'.format(inputt))
            cmd = compose_command(configs[key], input_file=inputt, output_path=output_path, output_file=output_tree, nproc=nproc)
            # sb.run(cmd, stdout=sb.DEVNULL, stderr=sb.DEVNULL, check=True))
            sb.check_call(cmd, stdout=sb.DEVNULL, stderr=sb.DEVNULL)
            t1 = time.time()
            info('{} generated in {}s\n'.format(output_tree, int(t1-t0)))
        except sb.CalledProcessError as cpe:
            error('{}'.format(cpe))
        except:
            error('error while executing {}'.format(' '.join(cmd)), exit=True)
    else:
        info('Phylogeny {} already built\n'.format(output_tree))


def refine_phylogeny(configs, key, inputt, starting_tree, output_path, output_tree, nproc=1, verbose=False):
    if not os.path.isfile(output_tree):
        try:
            t0 = time.time()
            info('Refining phylogeny {}\n'.format(inputt))
            cmd = compose_command(configs[key], input_file=inputt, database=starting_tree, output_path=output_path, output_file=output_tree, nproc=nproc)
            # sb.run(cmd, stdout=sb.DEVNULL, stderr=sb.DEVNULL, check=True))
            sb.check_call(cmd, stdout=sb.DEVNULL, stderr=sb.DEVNULL)
            t1 = time.time()
            info('{} generated in {}s\n'.format(output_tree, int(t1-t0)))
        except sb.CalledProcessError as cpe:
            error('{}'.format(cpe))
        except:
            error('error while executing {}'.format(' '.join(cmd)), exit=True)
    else:
        info('Phylogeny {} already refined\n'.format(output_tree))


if __name__ == '__main__':
    args = read_params()
    project_name = check_args(args, verbose=args.verbose)

    if args.clean_all:
        clean_all(args.databases_folder, verbose=args.verbose)

    if args.clean:
        clean_project(args.data_folder, args.output_folder, verbose=args.verbose)

    configs = read_configs(args.config_file, verbose=args.verbose)
    check_configs(configs, verbose=args.verbose)
    check_dependencies(configs, args.nproc, verbose=args.verbose)
    db_dna, db_aa = init_database(args.database, args.databases_folder, configs, '', 'db_aa', verbose=args.verbose)

    if not args.meta: # standard phylogeny reconstruction
        input_fna = load_input_files(args.input_folder, args.data_folder+'bz2/', args.genome_extension, verbose=args.verbose)

        if input_fna:
            gene_markers_identification(configs, 'map_dna', input_fna, args.data_folder+'map_dna/', args.database, db_dna, args.min_num_proteins, nproc=args.nproc, verbose=args.verbose)
            gene_markers_selection(args.data_folder+'map_dna/', largest_cluster, args.min_num_proteins, nproc=args.nproc, verbose=args.verbose)
            gene_markers_extraction(input_fna, args.data_folder+'map_dna/', args.data_folder+'markers_dna/', args.genome_extension, nproc=args.nproc, verbose=args.verbose)
            fake_proteome(args.data_folder+'markers_dna/', args.data_folder+'fake_proteomes/', args.genome_extension, args.proteome_extension, nproc=args.nproc, verbose=args.verbose)

        faa = load_input_files(args.input_folder, args.data_folder+'bz2/', args.proteome_extension, verbose=args.verbose)
        input_faa = load_input_files(args.data_folder+'fake_proteomes/', args.data_folder+'bz2/', args.proteome_extension, verbose=args.verbose)
        input_faa.update(faa) # if duplicates input keep the ones from 'faa'

        if input_faa:
            input_faa_checked = check_input_proteomes(input_faa, args.min_num_proteins, args.min_len_protein, args.data_folder, nproc=args.nproc, verbose=args.verbose)

            if input_faa_checked:
                clean_input_proteomes(input_faa_checked, args.data_folder+'clean_aa/', nproc=args.nproc, verbose=args.verbose)
                input_faa_clean = load_input_files(args.data_folder+'clean_aa/', args.data_folder+'bz2/', args.proteome_extension, verbose=args.verbose)

                if input_faa_clean:
                    gene_markers_identification(configs, 'map_aa', input_faa_clean, args.data_folder+'map_aa/', args.database, db_aa, args.min_num_proteins, nproc=args.nproc, verbose=args.verbose)
                    gene_markers_selection(args.data_folder+'map_aa/', best_hit, args.min_num_proteins, nproc=args.nproc, verbose=args.verbose)
                    gene_markers_extraction(input_faa_clean, args.data_folder+'map_aa/', args.data_folder+'markers_aa/', args.proteome_extension, args.min_num_markers, nproc=args.nproc, verbose=args.verbose)

        inputs2markers(args.data_folder+'markers_aa/', args.proteome_extension, args.data_folder+'markers/', verbose=args.verbose)
        inp_f = args.data_folder+'markers/'

        if args.integrate:
            input_integrate = integrate(inp_f, args.databases_folder+args.database, args.data_folder, nproc=args.nproc, verbose=args.verbose)

        out_f = args.data_folder+'msas/'
        msas(configs, 'msa', inp_f, args.proteome_extension, out_f, nproc=args.nproc, verbose=args.verbose)
        inp_f = out_f

        if args.trim:
            if 'trim' in configs and ((args.trim == 'gappy') or (args.trim == 'greedy')):
                out_f = args.data_folder+'trim_gappy/'
                trim_gappy(configs, 'trim', inp_f, out_f, nproc=args.nproc, verbose=args.verbose)
                inp_f = out_f

            if (args.trim == 'not_variant') or (args.trim == 'greedy'):
                out_f = args.data_folder+'trim_not_variant/'
                trim_not_variant(inp_f, out_f, threshold=args.not_variant_threshold, nproc=args.nproc, verbose=args.verbose)
                inp_f = out_f

        if args.remove_fragmentary_entries:
            out_f = args.data_folder+'fragmentary/'
            remove_fragmentary_entries(inp_f, out_f, threshold=args.fragmentary_threshold, verbose=args.verbose)
            inp_f = out_f

        if args.subsample:
            out_f = args.data_folder+'sub/'
            # subsample(inp_f, out_f, args.subsample, trident, args.submat_folder, args.submat, nproc=args.nproc, verbose=args.verbose)
            subsample(inp_f, out_f, args.subsample, args.scoring_function, args.submat_folder+args.submat+'.pkl', nproc=args.nproc, verbose=args.verbose)
            inp_f = out_f

        if 'gene_tree1' in configs:
            out_f = args.data_folder+'gene_tree1/'
            build_gene_tree(configs, 'gene_tree1', inp_f, out_f, nproc=args.nproc, verbose=args.verbose)

            if 'gene_tree2' in configs:
                outt = args.data_folder+'gene_tree2/'
                refine_gene_tree(configs, 'gene_tree2', inp_f, out_f, outt, nproc=args.nproc, verbose=args.verbose)
                out_f = outt

            inp_f = out_f
            out_f = args.data_folder+'gene_trees.tre'
            merging_gene_trees(inp_f, out_f, verbose=args.verbose)
            inp_f = out_f
        else:
            all_inputs = (i[i.rfind('/')+1:i.rfind('.')] for i in input_faa_clean)

            if args.integrate:
                all_inputs = (a for a in list(all_inputs)+list(input_integrate))

            out_f = args.data_folder+'all.aln'
            concatenate(all_inputs, inp_f, out_f, sort=args.sort, verbose=args.verbose)
            inp_f = out_f

        out_f = args.output_folder+project_name+'.tre'
        build_phylogeny(configs, 'tree1', inp_f, os.path.abspath(args.output_folder), out_f, nproc=args.nproc, verbose=args.verbose)
        inp_f = out_f

        if 'tree2' in configs:
            outt = args.output_folder+project_name+'_refine.tre'
            refine_phylogeny(configs, 'tree2', inp_f, out_f, os.path.abspath(args.output_folder), outt, nproc=args.nproc, verbose=args.verbose)
    else: # metagenomic application
        pass

    sys.exit(0)