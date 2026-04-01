import os

import pandas as pd

def compare_files(file1, file2, output_dir, date_columns, sort_columns):
    # Load the files into DataFrames
    df1 = pd.read_csv(file1)
    df2 = pd.read_csv(file2)

    # Drop date columns and sort both DataFrames
    df1_normalized = df1.drop(columns=date_columns, errors='ignore').sort_values(by=sort_columns).reset_index(drop=True)
    df2_normalized = df2.drop(columns=date_columns, errors='ignore').sort_values(by=sort_columns).reset_index(drop=True)

    # Write differences to separate files
    diff1_file = os.path.join(output_dir, 'differences_in_file1.csv')
    diff2_file = os.path.join(output_dir, 'differences_in_file2.csv')

    df1_normalized.to_csv(diff1_file, index=False)
    df2_normalized.to_csv(diff2_file, index=False)

    # Compare the normalized DataFrames
    if df1_normalized.equals(df2_normalized):
        print("The files contain the same data (excluding dates).")
    else:
        print("The files have differences:")
        # Highlight differences
        diff1 = df1_normalized[~df1_normalized.isin(df2_normalized)].dropna()
        diff2 = df2_normalized[~df2_normalized.isin(df1_normalized)].dropna()
        print("In file1 but not in file2:\n", diff1)
        print("In file2 but not in file1:\n", diff2)

# Example usage
compare_files(r'Z:\SRC\2020s\2025\JC28302\BioChem\JC28302_BCD_D.csv',
              r'C:\Users\upsonp\PycharmProjects\dart\reports\JC28302_BCD_D.csv',
              output_dir=r'C:\Users\upsonp\PycharmProjects\dart\reports',
              date_columns=['dis_data_num', 'date_column1', 'date_column2'],
              sort_columns=['dis_detail_collector_samp_id', 'dis_detail_data_type_seq'])