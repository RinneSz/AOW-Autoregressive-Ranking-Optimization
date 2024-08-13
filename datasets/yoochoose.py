from .base import AbstractDataset
from .utils import *

from datetime import date
from pathlib import Path
import pickle
import shutil
import tempfile
import os

import numpy as np
import pandas as pd
from tqdm import tqdm
tqdm.pandas()


class YooChooseDataset(AbstractDataset):
    @classmethod
    def code(cls):
        return 'yoochoose'

    @classmethod
    def url(cls):
        return 'https://s3-eu-west-1.amazonaws.com/yc-rdata/yoochoose-data.7z'

    @classmethod
    def zip_file_content_is_folder(cls):
        return True

    @classmethod
    def all_raw_file_names(cls):
        return ['dataset-README.txt',
                'yoochoose-test.dat',
                'yoochoose-clicks.dat',
                'yoochoose-buys.dat']

    @classmethod
    def is_zipfile(cls):
        return False

    @classmethod
    def is_7zfile(cls):
        return True

    def maybe_download_raw_dataset(self):
        folder_path = self._get_rawdata_folder_path()
        if folder_path.is_dir() and\
           all(folder_path.joinpath(filename).is_file() for filename in self.all_raw_file_names()):
            print('Raw data already exists. Skip downloading')
            return
        
        print("Raw file doesn't exist. Downloading...")
        download(self.url(), 'file.7z')
        unzip7z('file.7z')
        os.remove('file.7z')
        os.mkdir(folder_path)
        for item in self.all_raw_file_names():
            shutil.move(item, folder_path.joinpath(item))
        print()

    def preprocess(self):
        dataset_path = self._get_preprocessed_dataset_path()
        if dataset_path.is_file():
            print('Already preprocessed. Skip preprocessing')
            return
        if not dataset_path.parent.is_dir():
            dataset_path.parent.mkdir(parents=True)
        self.maybe_download_raw_dataset()
        df = self.load_ratings_df()
        df = self.filter_triplets(df)
        df, umap, smap = self.densify_index(df)
        train, val, test = self.split_df(df, len(umap))
        dataset = {'train': train,
                   'val': val,
                   'test': test,
                   'umap': umap,
                   'smap': smap}
        with dataset_path.open('wb') as f:
            pickle.dump(dataset, f)

    def load_ratings_df(self):
        folder_path = self._get_rawdata_folder_path()
        file_path = folder_path.joinpath('yoochoose-clicks.dat')
        df = pd.read_csv(file_path, header=None)
        df.columns = ['uid', 'timestamp', 'sid', 'category']
        return df
