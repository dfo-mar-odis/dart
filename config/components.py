from enum import Enum
from bs4 import BeautifulSoup

from django.template.loader import render_to_string


class completed(Enum):
    none = 0
    success = 1
    failure = 2


def modal(title, completion: completed=completed.none, swap_oob=False, minvalue=0, maxvalue=100):
    html = render_to_string(template_name="modal.html")
    ws_modal_soup = BeautifulSoup(html, 'html.parser')
    ws_modal = ws_modal_soup.find('div')

    ws_dialog = ws_modal.find(id='modalDialog')
    if swap_oob:
        ws_dialog.attrs['hx-swap-oob'] = 'true'

    ws_title = ws_dialog.find(id="modalTitle")
    ws_title.string = title
    ws_progress = ws_modal.find(id="modalProgressBar")
    ws_sub_progress = ws_progress.find('div')

    if completion != completed.none:
        minvalue = maxvalue
        attrs = {'type': 'button', 'class': 'btn-close', 'data-bs-dismiss': 'modal', 'aria-label': 'Close'}

        ws_sub_progress['class'].remove("progress-bar-striped")

        header = ws_dialog.find(id="modalContent").find('div')
        header.append(ws_modal_soup.new_tag('button', attrs=attrs))

    percentage = int((minvalue/maxvalue)*100)
    ws_progress.attrs["aria-valuenow"] = str(percentage)
    ws_progress.attrs["aria-valuemin"] = str(minvalue)
    ws_progress.attrs["aria-valuemax"] = str(maxvalue)
    ws_sub_progress['style'] = f"width: {percentage}%"
    ws_sub_progress.string = f"{percentage}%"
    if completion == completed.success:
        ws_sub_progress['class'].append("bg-success")
    elif completion == completed.failure:
        ws_sub_progress['class'].append("bg-danger")
        ws_sub_progress.string = ""

    return ws_dialog


def websocket_modal(title, logger_name, path=None):
    html = render_to_string(template_name="modal.html")
    ws_modal_soup = BeautifulSoup(html, 'html.parser')

    ws_dialog = ws_modal_soup.find(id='modalDialog')
    ws_dialog.attrs['hx-swap-oob'] = 'true'

    if path:
        ws_dialog.attrs['hx-post'] = path
        ws_dialog.attrs['hx-trigger'] = 'load'
    ws_dialog.attrs['hx-ext'] = 'ws'
    ws_dialog.attrs['ws-connect'] = f"/ws/notification/{logger_name}/"

    ws_title = ws_dialog.find(id="modalTitle")
    ws_title.string = title

    return ws_dialog