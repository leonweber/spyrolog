# sPyrolog
A Prolog interpreter with support for weak unification (two symbols can unify if they are sufficiently similar)

This project is a fork of sPyrolog is a fork of the [Prolog interpreter Pyrolog](https://bitbucket.org/cfbolz/pyrolog/).

## Build
sPyrolog is written in RPython and can be compiled with

```pypy-6.0.0-linux_x86_64-portable/bin/rpython targetprologstandalone.py -oJIT```

## Usage
While sPyrolog should support arbitrary Prolog programs, it has been written for use in [NLProlog](https://github.com/leonweber/nlprolog) and was only tested in this context.

A sPyrolog program consists of two files:

The `facts` file contains the facts and rules of the Prolog program in the following syntax: `[statement] = [score]`
A very simple example program would be:

```
country(X,Z) :- is_in(X,Y), country(Y,Z). = 1.0
country(berlin, germany). = 1.0
is_located_in(berlin, germany). = 0.8
is_located_in(X,Z) :- is_in(X,Y), country(Y,Z). = 0.8
```

The `similarity` file contains similarities between the symbols of the `facts` file:

```
country ~ is_located_in = 0.8
```

Note, that this implemenation requires that the weak unification for predicate symbols with rule heads and facts has to be done in a preprocessing step.
For instance, the similarity `country ~ is_located_in = 0.8` makes unification of `country` and `is_located_in` posssible.
For sPyrolog to respect this, the fact `is_located_in(berlin, germany). = 0.8` derived from `country(berlin, germany). = 1.0` has to be included in the `facts` file.
