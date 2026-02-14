"""Основной модуль CLI для prefixopt"""
import typer
import os
import sys

# Импортируем модули команд
from .cli import optimize as opt_cmd
from .cli import filter as flt_cmd
from .cli import merge as mrg_cmd
from .cli import subnet as sub_cmd
from .cli import stats as stat_cmd
from .cli import exclude as exc_cmd
from .cli import diff as diff_cmd

# Инициализация приложения
app = typer.Typer(add_completion=False)

# Регистрация команд
# Берем функцию из модуля и вешаем на нее декоратор app.command

app.command(name="optimize")(opt_cmd.optimize)
app.command(name="add")(opt_cmd.add)

app.command(name="filter")(flt_cmd.filter)

app.command(name="merge")(mrg_cmd.merge)
app.command(name="intersect")(mrg_cmd.intersect)

app.command(name="split")(sub_cmd.split)

app.command(name="stats")(stat_cmd.stats)
app.command(name="check")(stat_cmd.check)

app.command(name="exclude")(exc_cmd.exclude)

app.command(name="diff")(diff_cmd.diff)

if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    app()