import time

import pytest


def test_benchmark1(benchmark):
    @benchmark
    def something():
        time.sleep(0.000001)


def test_benchmark2(benchmark):
    @benchmark
    def something():
        time.sleep(0.001)


@pytest.mark.benchmark(group="group1")
def test_slow(benchmark):
    @benchmark
    def something():
        time.sleep(0.1)


@pytest.mark.benchmark(group="group1")
def test_normal(benchmark):
    @benchmark
    def something():
        time.sleep(0.01)


@pytest.mark.benchmark(group="group1")
def test_fast(benchmark):
    @benchmark
    def something():
        time.sleep(0.001)


@pytest.mark.benchmark(group="group2")
def test_slow2(benchmark):
    @benchmark
    def something():
        time.sleep(0.1)


@pytest.mark.benchmark(group="group2")
def test_normal2(benchmark):
    @benchmark
    def something():
        time.sleep(0.01)


@pytest.mark.benchmark(group="group2")
def test_fast2(benchmark):
    @benchmark
    def something():
        time.sleep(0.001)
