from .base import AbstractDataloader

import torch
import random
import torch.utils.data as data_utils
import numpy as np


class TESTDataloader():
    def __init__(self, args, dataset):
        self.args = args
        self.rng = random.Random()
        self.save_folder = dataset._get_preprocessed_folder_path()
        dataset = dataset.load_dataset()
        # user and item IDs start from 1
        self.train = dataset['train']
        self.val = dataset['val']
        self.test = dataset['test']
        self.umap = dataset['umap']
        self.smap = dataset['smap']

        self.user_count = len(self.umap)
        self.item_count = len(self.smap)

        item_frequency = list([0 for i in range(self.item_count)])
        average_len = 0
        for key in self.train.keys():
            average_len += len(self.train[key])
            for item in self.train[key]:
                item_frequency[item-1] += 1
        for key in self.val.keys():
            for item in self.val[key]:
                item_frequency[item-1] += 1
        for key in self.test.keys():
            for item in self.test[key]:
                item_frequency[item-1] += 1
        if args.method == 'cold':
            candidate_items = np.load('./sequence pattern/cold watermark seq %s %d %s %d.npy' % (
                args.dataset_code, args.pattern_len, args.model_code, args.bottom_m))
        elif args.method == 'pop':
            candidate_items = np.load('./sequence pattern/pop watermark seq %s %d %s %d.npy' % (
                args.dataset_code, args.pattern_len, args.model_code, args.bottom_m))

        else:
            raise ValueError('Please check the method parameter!')

        print('Candidate Items:', candidate_items)
        # print('Target Item:', target_item)
        # print('Average Length:', average_len)

        number_test_seqs = 1000
        self.valid_users = []
        for i in range(number_test_seqs):
            new_user_idx = self.user_count + i + 1
            self.valid_users.append(new_user_idx)
            length = np.random.randint(2, len(candidate_items)+1)
            whole_sequence = list(candidate_items[:length])
            self.train[new_user_idx] = whole_sequence[:-1]
            self.val[new_user_idx] = []
            self.test[new_user_idx] = [whole_sequence[-1]]

        args.num_items = self.item_count
        self.max_len = args.bert_max_len
        self.mask_prob = args.bert_mask_prob
        self.max_predictions = args.bert_max_predictions
        self.sliding_size = args.sliding_window_size
        self.CLOZE_MASK_TOKEN = self.item_count + 1

    @classmethod
    def code(cls):
        return 'bert'

    def get_pytorch_dataloaders(self):
        train_loader = self._get_train_loader()
        val_loader = self._get_val_loader()
        test_loader = self._get_test_loader()
        return train_loader, val_loader, test_loader

    def _get_train_loader(self):
        dataset = self._get_train_dataset()
        dataloader = data_utils.DataLoader(dataset, batch_size=self.args.train_batch_size,
                                           shuffle=True, pin_memory=True)
        return dataloader

    def _get_train_dataset(self):
        dataset = TESTTrainDataset(
            self.train, self.max_len, self.mask_prob, self.max_predictions, self.sliding_size, self.CLOZE_MASK_TOKEN, self.item_count, self.rng)
        return dataset

    def _get_val_loader(self):
        return self._get_eval_loader(mode='val')

    def _get_test_loader(self):
        return self._get_eval_loader(mode='test')

    def _get_eval_loader(self, mode):
        batch_size = self.args.val_batch_size if mode == 'val' else self.args.test_batch_size
        dataset = self._get_eval_dataset(mode)
        dataloader = data_utils.DataLoader(dataset, batch_size=batch_size, shuffle=False, pin_memory=True)
        return dataloader

    def _get_eval_dataset(self, mode):
        if mode == 'val':
            dataset = TESTValidDataset(self.train, self.val, self.max_len, self.CLOZE_MASK_TOKEN, valid_users=self.valid_users)
        elif mode == 'test':
            dataset = TESTTestDataset(self.train, self.val, self.test, self.max_len, self.CLOZE_MASK_TOKEN, self.args.model_code, test_users=self.valid_users)
        return dataset


class TESTTrainDataset(data_utils.Dataset):
    def __init__(self, u2seq, max_len, mask_prob, max_predictions, sliding_size, mask_token, num_items, rng):
        # self.u2seq = u2seq
        # self.users = sorted(self.u2seq.keys())
        self.max_len = max_len
        self.mask_prob = mask_prob
        self.max_predictions = max_predictions
        self.sliding_step = int(sliding_size * max_len)
        self.mask_token = mask_token
        self.num_items = num_items
        self.rng = rng

        assert self.sliding_step > 0
        self.all_seqs = []
        for u in sorted(u2seq.keys()):
            seq = u2seq[u]
            if len(seq) < self.max_len + self.sliding_step:
                self.all_seqs.append(seq)
            else:
                start_idx = range(len(seq) - max_len, -1, -self.sliding_step)
                self.all_seqs = self.all_seqs + [seq[i:i + max_len] for i in start_idx]

    def __len__(self):
        return len(self.all_seqs)
        # return len(self.users)

    def __getitem__(self, index):
        # user = self.users[index]
        # seq = self._getseq(user)
        seq = self.all_seqs[index]

        tokens = []
        labels = []
        covered_items = set()
        for i in range(len(seq)):
            s = seq[i]
            if (len(covered_items) >= self.max_predictions) or (s in covered_items):
                tokens.append(s)
                labels.append(0)
                continue

            temp_mask_prob = self.mask_prob
            if i == (len(seq) - 1):
                temp_mask_prob += 0.1 * (1 - self.mask_prob)

            prob = self.rng.random()
            if prob < temp_mask_prob:
                covered_items.add(s)
                prob /= temp_mask_prob
                if prob < 0.8:
                    tokens.append(self.mask_token)
                elif prob < 0.9:
                    tokens.append(self.rng.randint(1, self.num_items))
                else:
                    tokens.append(s)

                labels.append(s)
            else:
                tokens.append(s)
                labels.append(0)

        tokens = tokens[-self.max_len:]
        labels = labels[-self.max_len:]

        mask_len = self.max_len - len(tokens)

        tokens = [0] * mask_len + tokens
        labels = [0] * mask_len + labels

        return torch.LongTensor(tokens), torch.LongTensor(labels)

    def _getseq(self, user):
        return self.u2seq[user]


class TESTValidDataset(data_utils.Dataset):
    def __init__(self, u2seq, u2answer, max_len, mask_token, valid_users=None):
        self.u2seq = u2seq  # train
        if not valid_users:
            self.users = sorted(self.u2seq.keys())
        else:
            self.users = valid_users
        self.u2answer = u2answer
        self.max_len = max_len
        self.mask_token = mask_token

    def __len__(self):
        return len(self.users)

    def __getitem__(self, index):
        user = self.users[index]
        seq = self.u2seq[user]
        answer = self.u2answer[user]

        candidates = answer
        labels = [1] * len(answer)

        seq = seq + [self.mask_token]
        seq = seq[-self.max_len:]
        padding_len = self.max_len - len(seq)
        seq = [0] * padding_len + seq

        return torch.LongTensor(seq), torch.LongTensor(candidates), torch.LongTensor(labels)


class TESTTestDataset(data_utils.Dataset):
    def __init__(self, u2seq, u2val, u2answer, max_len, mask_token, model_code, test_users=None):
        self.u2seq = u2seq  # train
        self.u2val = u2val  # val
        if not test_users:
            self.users = sorted(self.u2seq.keys())
        else:
            self.users = test_users
        # self.users = sorted(self.u2seq.keys())
        self.u2answer = u2answer  # test
        self.max_len = max_len
        self.mask_token = mask_token
        self.model_code = model_code

    def __len__(self):
        return len(self.users)

    def __getitem__(self, index):
        user = self.users[index]
        seq = self.u2seq[user] + self.u2val[user]  # append validation item after train seq
        answer = self.u2answer[user]

        candidates = answer
        labels = [1] * len(answer)

        if self.model_code == 'bert':
            seq = seq + [self.mask_token]
        seq = seq[-self.max_len:]
        padding_len = self.max_len - len(seq)
        seq = [0] * padding_len + seq

        return torch.LongTensor(seq), torch.LongTensor(candidates), torch.LongTensor(labels)