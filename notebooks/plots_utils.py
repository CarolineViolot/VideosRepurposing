def get_politic_news_color_maps():
    return {"Far Left":'#AA2828', 'Left':'#D27878', 'Center':'#F0C8B9', 'Right':'#B9D2E6', 'Far Right':'#AF823C',
            "Left (news)":'#567572', "Center (news)": '#B8B8B8', "Right (news)":'#384D6C'}

def get_parties_color_maps():
    return {
        # Far Left — dark reds
        'LO':   '#5C0002', 'NPA':  '#8B0000',
        # Left — reds / warm
        'LFI':  '#C1121F', 'PCF':  '#E01E37',
        'EELV': '#52B788',# greens for ecologists
        'PS':   '#F94144', 'PP':   '#2D6A4F',

        # Center — orange / amber / yellow
        'RE':   '#F9A825', 'UDI':  '#FFD166', 'HOR':  '#F4A261', #'MoDem':'#FF7B00',
        # Right — light-to-mid blues
        'UPR':  '#90E0EF', 'LR':   '#457B9D', 'DLF':  '#0096C7',
        # Far Right — dark blues / navy
        'RN':   '#1D3557', 'LP':   '#023E8A', 'REC':  '#03045E',
    }

def get_plt_attr():
    rcParams = {'font.size': 8, 'font.family': "serif"}

    shorts_style = {'color': 'k', 'linestyle': '-', 'linewidth': 0.8, "label": "Shorts"}
    RV_style = {'color': 'k', 'linestyle': '--', 'linewidth': 0.8, "label": "Regular"}

    column_width = 3.32492194445
    sep_width = 0.3764061111113
    page_width = 2 * column_width + sep_width
    return rcParams, column_width, page_width, shorts_style, RV_style

