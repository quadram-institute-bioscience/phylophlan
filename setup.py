import setuptools
from io import open
import sys
from subprocess import call


if sys.version_info[0] < 3:
    sys.stdout.write('PhyloPhlAn requires Python 3 or higher. Please update you Python installation')


install_reqs = ["biopython", "dendropy", "matplotlib", "numpy", "pandas", "seaborn"]

setuptools.setup(name='PhyloPhlAn',
                 version='3.0',
                 author='Francesco Asnicar',
                 author_email='f.asnicar@unitn.it',
                 url='http://github.com/biobakery/phylophlan',
                 license='license.txt',
                 scripts=[],
                 packages=setuptools.find_packages(),
                 package_data={
                     'phylophlan': [
                         'phylophlan_configs/*',
                         'phylophlan_substitution_matrices/*',
                         'phylophlan_substitution_models/*',
                         'phylophlan_write_default_configs.sh'
                 ]},
                 include_package_date=True,
                 entry_points={
                     'console_scripts': [
                         'phylophlan = phylophlan.phylophlan:phylophlan_main',
                         'phylophlan_draw_metagenomic = phylophlan.phylophlan_draw_metagenomic:phylophlan_draw_metagenomic',
                         'phylophlan_get_reference = phylophlan.phylophlan_get_reference:phylophlan_get_reference',
                         'phylophlan_metagenomic = phylophlan.phylophlan_metagenomic:phylophlan_metagenomic',
                         'phylophlan_setup_database = phylophlan.phylophlan_setup_database:phylophlan_setup_database',
                         'phylophlan_strain_finder = phylophlan.phylophlan_strain_finder:phylophlan_strain_finder',
                         'phylophlan_write_config_file = phylophlan.phylophlan_write_config_file:phylophlan_write_config_file'
                 ]},
                 description='Precise phylogenetic analysis of microbial isolates and genomes from metagenomes',
                 long_description=open('readme.md').read(),
                 long_description_content_type='text/markdown',
                 install_requires=install_reqs,
                 zip_safe=False)

call(['sh',
      'phylophlan/phylophlan_write_default_configs.sh',
      sys.prefix + '/lib/python{}.{}/site-packages/phylophlan/phylophlan_configs'.format(sys.version_info[0], sys.version_info[1])])
