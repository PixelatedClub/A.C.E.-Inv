"""Smoke test widgets and HTTP loading without modifying records."""
from .client import Client
from .server import DEFAULT_DATA


def main():
    app=Client(DEFAULT_DATA/'test_williams.json')
    app.withdraw()
    app.refresh()
    assert app.state['items'], 'API inventory did not load'
    assert len(app.notebook.tabs())==5
    assert app.state['account']['role']=='operator'
    app.item(False)
    app.update_idletasks()
    for child in app.winfo_children():
        if child.winfo_class()=='Toplevel':child.destroy()
    app.destroy()
    print('Desktop smoke test passed: five tabs, API records, operator role, new-item dialog.')


if __name__=='__main__':main()
