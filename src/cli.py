import os
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import Manager
from pathlib import Path

import argparse
import pandas
import polars as pl
from tqdm import tqdm

from .turning import generate_turning

PROC_FN = {
    "turning": generate_turning,
}


class _LocalFunctions:
    @classmethod
    def add_functions(cls, *args):
        for function in args:
            setattr(cls, function.__name__, function)
            function.__qualname__ = cls.__qualname__ + '.' + function.__name__


def save_result(df: pandas.DataFrame | pl.DataFrame, path_in: str, path_out: str):
    path_in = path_in.split("/")
    date = path_in[-3]
    under = path_in[-2]
    path_out = Path(path_out) / f"{date}_{under}.csv"

    if not os.path.exists(path_out):
        f = open(path_out, "x")
        f.write(",".join(df.columns) + "\n")
        f.close()

    if isinstance(df, pandas.DataFrame):
        df.to_csv(path_out, index=False, header=False, mode="a")
    elif isinstance(df, pl.DataFrame):
        f = open(path_out, "ab")
        df.write_csv(f, include_header=False)
        f.close()
    else:
        raise ValueError(f"Invalid dataframe type: {type(df)}")


def do_generate(in_dir: str, out_dir: str, kind: str, workers: int = None):
    if not os.path.exists(in_dir):
        raise FileNotFoundError(f"Directory {in_dir} does not exist")
    os.makedirs(out_dir, exist_ok=True)
    if kind not in PROC_FN:
        raise ValueError(f"Invalid report type to generate: {kind}")

    raw_files = list(Path(in_dir).rglob("*.parquet.gzip"))
    if not len(raw_files):
        raise FileNotFoundError(f"No files to process in {in_dir}")

    fn = PROC_FN[kind]
    if workers and workers > 1:
        def par_fn(lock, path_in: str, path_out: str):
            try:
                df = fn(path_in)
                with lock:
                    save_result(df, path_in, path_out)

            except Exception as e:
                return e
        _LocalFunctions.add_functions(par_fn)

        pool = ProcessPoolExecutor()
        m = Manager()
        lock = m.Lock()
        for result in tqdm(
            pool.map(
                par_fn,
                [lock] * len(raw_files),
                [str(file) for file in raw_files],
                [out_dir] * len(raw_files),
            ),
            total=len(raw_files),
        ):
            if result:
                raise result
    else:
        for file in tqdm(raw_files):
            df = fn(str(file))
            save_result(df, str(file), out_dir)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="Midas Options CLI")
    parser.add_argument(
        "in_dir",
        type=str,
        help="Directory containing the raw OPRA data",
    )
    parser.add_argument(
        "out_dir",
        type=str,
        help="Directory to save the generated reports",
    )
    parser.add_argument(
        "kind",
        type=str,
        help="Type of report to generate",
    )
    parser.add_argument(
        "--workers",
        type=int,
        help="Number of workers to use for multiprocessing",
    )
    args = parser.parse_args()
    do_generate(args.in_dir, args.out_dir, args.kind, args.workers)
