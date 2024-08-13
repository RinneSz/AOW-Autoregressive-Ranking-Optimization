from datasets import dataset_factory
from config import STATE_DICT_KEY
import argparse
import torch
from model import *
from dataloader.test import *
from trainer import *
from utils import *


'''test watermark validity on finetuned model'''


def train(args, export_root=None, resume=False):
    args.lr = 0.001
    # fix_random_seed_as(args.model_init_seed)

    dataset = dataset_factory(args)
    dataloader = TESTDataloader(args, dataset)
    train_loader, val_loader, test_loader = dataloader.get_pytorch_dataloaders()

    if args.model_code == 'bert':
        model = BERT(args)
    elif args.model_code == 'sas':
        model = SASRec(args)

    if export_root == None:
        if args.gold:
            export_root = 'experiments/' + args.model_code + '_finetune/' + args.dataset_code
        else:
            export_root = 'experiments/watermark_test_after_finetune/method_' + str(args.method) + '/' + args.model_code + '/' + \
                          args.dataset_code + '/' + str(args.number_ood_seqs) + '_' + str(args.number_ood_val_seqs) + \
                          '_' + str(args.pattern_len) + '_' + str(args.bottom_m) + '_' + str(args.finetune_ratio)

    model.load_state_dict(torch.load(os.path.join(export_root, 'models', 'best_acc_model.pth'), map_location='cpu').get(STATE_DICT_KEY))

    if args.model_code == 'bert':
        trainer = BERTTrainer(args, model, train_loader, val_loader, test_loader, export_root)
    if args.model_code == 'sas':
        trainer = SASTrainer(args, model, train_loader, val_loader, test_loader, export_root)

    trainer.test(test_watermark=True)


if __name__ == "__main__":
    set_template(args)

    batch = 128
    args.num_epochs = 1000
    args.train_batch_size = batch
    args.val_batch_size = batch
    args.test_batch_size = batch

    # when use k-core beauty and k is not 5 (beauty-dense)
    # args.min_uc = k
    # args.min_sc = k


    train(args, resume=False)
