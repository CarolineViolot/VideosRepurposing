import os
from src.file_io import load_channels_files
import pandas as pd
import json

if os.path.isdir("../data/"):
    os.chdir("../")

def create_tt_username2display_name(dict_file = 'data/dict/tt_username2display_name.json'):
    channels = load_channels_files()
    tt_channels = pd.concat([channels['news_tiktok_channels'], channels['pp_tiktok_channels']])
    tt_username2display_name = dict(zip(tt_channels.index, tt_channels['channelTitle']))
    with open(dict_file, 'w') as f:
        json.dump(tt_username2display_name, f, indent=2)