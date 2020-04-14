import pandas as pd
import matplotlib.pyplot as plt


def rename_columns(name):
    if name == 'Score Error (99.9%)':
        return 'error'
    else:
        return str.lower(name).replace('param: ', '')


def plot(input):
    df = pd.read_csv(input)
    df = df.rename(rename_columns, axis='columns')\
        .drop(columns=['mode', 'threads', 'samples', 'unit'])
    df.loc[df['benchmark'] == 'intersectionNoOffset', 'offset'] = 0
    df.loc[df['benchmark'] == 'intersectionWithConstantOffset0', 'offset'] = 0
    df.loc[df['benchmark'] == 'intersectionWithConstantOffset256', 'offset'] = 256
    df.loc[df['benchmark'] == 'intersectionWithConstantOffset512', 'offset'] = 512
    df.loc[df['benchmark'] == 'intersectionWithConstantOffset768', 'offset'] = 768
    df.loc[df['benchmark'] == 'intersectionNoOffset:ld_blocks_partial.address_alias', 'offset'] = 0
    df.loc[df['benchmark'] == 'intersectionWithConstantOffset0:ld_blocks_partial.address_alias', 'offset'] = 0
    df.loc[df['benchmark'] == 'intersectionWithConstantOffset256:ld_blocks_partial.address_alias', 'offset'] = 256
    df.loc[df['benchmark'] == 'intersectionWithConstantOffset512:ld_blocks_partial.address_alias', 'offset'] = 512
    df.loc[df['benchmark'] == 'intersectionWithConstantOffset768:ld_blocks_partial.address_alias', 'offset'] = 768
    df.loc[df['benchmark'].str.contains('ld_blocks_partial.address_alias'), 'error'] = 0
    filter = df['benchmark'].str.contains('ld_blocks_partial.address_alias')
    df['r/w offset'] = ((df['sourcesize'] - df['offset'] + df['padding']) * 8) + 16
    df.drop(columns=['offset', 'padding', 'targetsize', 'sourcesize'])
    thrpt = df[~filter]
    clean = thrpt['error'] < 1.0
    throughput = pd.pivot_table(thrpt[clean], values=['score', 'error'], index=['r/w offset'], columns=['benchmark'])
    aliases = pd.pivot_table(df[filter], values=['score', 'error'], index=['r/w offset'], columns=['benchmark'])
    fig = plt.figure()
    fig.set_size_inches(15, 10)
    aliases.plot(kind='line', yerr='error', y='score', ax=fig.add_subplot(111), title='ld_blocks_partial.address_alias')
    fig.savefig(f'aliases.png')

    fig = plt.figure()
    fig.set_size_inches(15, 10)
    throughput.plot(kind='line', yerr='error', y='score', ax=fig.add_subplot(111), title='Throughput (ops/μs)')
    fig.savefig(f'throughput.png')



plot('perfnorm.csv')