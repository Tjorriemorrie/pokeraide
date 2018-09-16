One hot encodings:
SB 0
BB 1
F 2
C/K 3
B/R 4
A 5


1 SB 1
2 BB 2
3 ?

h_HS
h_PO
? position
these stats are read on-demand, but it should be cachable
this will handle whether facing aggression
for f1-f5:

    incorporate before and after for position and getting rivals too
    rvl_before
    rvl_after

    aggression included as that will be send when retrieving the data
    preflop_f%
    preflop_c/k%
    preflop_b/r%
    preflop_a%
