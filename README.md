# Sumo Integer Linear Programming (ILP) Scheduler

In the top division of sumo, wrestlers participate in 15-day tournaments
in which each wrestler fights one bout a day and cannot face the same opponent more than once in a tournament.
With 42 top-division wrestlers, there are a staggering number of possible tournaments,
so I became curious about finding tournaments fitting certain optimal criteria.
I could not figure out analytic solutions to some of these questions,
so I wrote this tool to encode sumo tournament scheduling as an integer linear programming problem
to generate some amusing tournaments, as well as to have an excuse to play around with an ILP tool.

This specifically started because I wondered how a sumo round-robin tournament can be scheduled
while still abiding by the "each wrestler fights once a day, every day" rule.
In more abstract terms you can phrase this problem as,
"If you have `N` items, how can you group all `N choose 2` pairs of these items into `N-1` groups
such that each item appears in each group exactly once?"
At the bottom of this document, I have an analytic solution to this for `N` that are powers of 2,
but I do not know how to generalize it to all even `N`.
I'm sure there is a good algorithm to solve this but I haven't figured it out.

If you are good at combinatorics and have figured out analytic solutions for some of these questions,
I would love to hear your reasoning (or to learn of a specific algorithm for finding such schedules).
Really, I tried thinking about it but didn't get anywhere.
Additionally, if you are an ILP expert and you can tell me how to improve these encodings, I would love to learn.

## How to Use

Developed using Python 3.9. I did not consciously make use of 3.9's features, but I would bet on needing 3.7+ at least.

Also requires [Python-MIP](https://www.python-mip.com/), which I chose because it was very easy to install: `pip install mip`.
I only used the default CBC solver; I do not know if I might get better results on my machine using Gurobi or CPlex.
Specs on the machine I used (a slightly dated desktop): Intel i7-4790, 16 GB of RAM.

You can run `python sumo_query.py -h` to see a description of the commands and options.

In the examples below, I give the commands I used. The default settings correspond to the top division (Makuuchi). 
You can generate tournaments for the second division (Juryo) by setting `N` to 28.

I made the encoding general enough to handle the divisions below Juryo, 
where wrestlers fight 7 times per tournament and so don't fight every day, 
but I was unable to get the solver to generate solutions using the real sizes of the lower divisions
within 5 minutes so I never actually tried these (for the third division, Makushita, `N` is 120, `D` is 15, `M` is 7, `UB` is 30, and `LB` is 20).
I do know the encoding works for `M != D` because I generated schedules using `N` at 42, `D` at 15, `M` at 7, and `LB` at 10.

For cosmetic purposes, I included files encoding wrestler names and ranks for Makuuchi and Juryo [here](names_files)
per the November 2020 ranks.
If you specify a names file, the schedules produced will include the wrestler names and indicate their correct side.
I transcribed the list manually, so I apologize if there are any typos or mistakes.

## Simplifying Assumptions

In real sumo tournaments, each day's matches
are decided by a committee of coaches and are typically announced during the previous day's bouts.
The scheduling committee is interested in putting on a good show for the audience, 
in making the race for the championship exciting, and following certain customs like
having the yokozuna and ozeki face low-ranked opponents in the first week and each other in the second week.
This tool is intended to model _possible_ tournaments rather than _likely_ ones, 
so for now I've at least not made any attempt to formalize
the unwritten (and often-changing) criteria used to make real scheduling decisions.

Additionally, tournaments are often complicated by wrestlers dropping out before the tournament starts
or during the tournament due to injuries, resulting in fewer bouts on some days and opponents from the
lower divisions being brought up to fight in the top division.
For simplicity, this tool elides some of these complexities, though it might be feasible to eventually support more of these.

1. We assume that all wrestlers participate on all days of the tournament, not requiring any "visitors" from the lower division.
2. We enforce no constraints about which matchups happen when, other than a "koreyori sanyaku" option I included (the highest-ranked fighters will only meet in the last bouts of the last day) and an option to provide a file specifying which matchups are not allowed due to wrestlers being in the same stable. (Conflict files for Makuuchi and Juryo are given [here](conflicts_files). I manually put it together based on looking at wrestlers' stables so I apologize for any transcription mistakes.)

We also do not model the results of playoffs, partly because the rules about playoffs between more than two wrestlers get very complicated.

## Encoding Description

(I would much prefer LaTeX for this. Alas...)

### Finding a Bout Schedule

Suppose there are `N` wrestlers participating in a `D`-day tournament, where `N` is even and each wrestler fights `M` bouts 
over the course of the tournament (up to 1 per day) and never faces the same opponent more than once in a tournament.
Each day there are at least `LB` bouts and at most `UB` bouts.

We can model these fights using a set of integer variables `f[i][j][d]` 
where `0 <= f[i][j][d] <= 1`, `0 <= i < N`, `i < j < N`, and `0 <= d < D`.
If `f[i][j][d]` is 1, that means wrestler `i` faces wrestler `j` on day `d` (all 0-based).

Each wrestler fights at most once a day (if `M` = `D` as in the top two divisions, then this is exactly once),
which we can encode by adding constraints of the form `sum_{0 <= j < i} f[j][i][d] + sum_{i < j < N} f[i][j][d] <= 1`
for each `0 <= i < N` and `0 <= d < D`.

Each wrestler fights a total of `M` times over the course of a tournament. We can encode this by adding constraints of the form
`sum_{0 <= d < D} sum_{0 <= j < i} f[j][i][d] + sum_{i < j < N} f[i][j][d] == M` for each `0 <= i < N`.

Any two opponents can face each other at most once in the same tournament, which we can encode with constraints of the form
`sum_{0 <= d < D} f[i][j][d] <= 1` for all `0 <= i < N` and `i < j < N`.

For scheduling purposes, we also enforce that each day of the tournament have at least `LB` total bouts and at most `UB` total bouts 
(if every wrestler fights every day and there are no absences, then you can set `LB = UB = N/2`).
This can be encoded using constraints like the following for each `0 <= d < D`:
```
sum_{0<=i<N} sum_{i<j<N} f_{i, j, d} <= UB
sum_{0<=i<N} sum_{i<j<N} f_{i, j, d} >= LB
```

### Modeling Victories and Scores

Given the above, let us define binary variables `w[i][j][d]` for all `0 <= i < N`, `i < j < N`, and `0 <= d < D`
where `w[i][j][d]` is 1 iff wrestler `i` defeated `j` on day `d` and 0 otherwise.
(I realize we can probably drop the `d` subscript since each matchup
can only happen once in any tournament, 
but this made it easier to track the score on any given day.
Perhaps reformulating this might be easier on the ILP solver.)

For `w[i][j][d]`, we only need one constraint, which is that `w[i][j][d] <= f[i][j][d]` for all valid `i`, `j`, and `d`,
since nobody can win a fight that didn't take place (unless Hakuho has developed an interdimensional technique).
Note that if `f[i][j][d]` is 1 and `w[i][j][d]` is 0, that means `j` won the bout. We will use this shortly.

To model the scores over the course of the tournament, let us define integer variables `s[i][d]` for all `0 <= i < N`
and `0 <= d < D`, where `s[i][d]` represents wrestler `i`'s score on day `d`.
First, let us note that `f[i][j][d] - w[i][j][d]` is 1 iff `i` and `j` fought on day `d` and `i` won
and 0 iff `i` and `j` did not fight on day `d` or `j` won the fight (since `w[i][j][d]` must be 0 if `f[i][j][d]` is 0).
Thus, for all `0 <= i < N` and `0 <= d < D`, `sum_{0 <= j < i} (f[j][i][d] - w[j][i][d]) + sum_{i < j < N} w[i][j][d]`
is 1 iff `i` fought on day `d` and won.
Thus, for all `0 <= i < N`, we add the constraint `s[i][0] == sum_{0 <= j < i} (f[j][i][0] - w[j][i][0]) + sum_{i < j < N} w[i][j][0]`
and for all `1 <= d < D`, we add the constraint `s[i][d] == s[i][d-1] + sum_{0 <= j < i} (f[j][i][d] - w[j][i][d]) + sum_{i < j < N} w[i][j][d]`.

### Conditions Modeled in my Queries

#### Who's the Champ?

Several of the below queries are concerned about conditions related to the champion.
In sumo, a wrestler is the champion if he has the most wins after the final day's bouts. 
If more than one wrestler is tied, then there is a tiebreaker playoff between them; we will not model the results of playoffs for now.

To specify that a given wrestler `i` is the champion (up to a tie), we simply need a constraint that the score of `i` on the final day (`D-1`) is greater than or equal to all others: `s[i][D-1] >= s[j][D-1]` for all `0 <= j < N` where `j != i`.
To exclude ties, we amend the condition to `s[i][D-1] > s[j][D-1]` (or `s[i][D-1] >= s[j][D-1] + 1` in the code, as `mip` only permits `>=` and `<=` constraints).

#### Mathematically Secure Championship

While most championships are decided on the final day and some go to a playoff, sometimes a sumo championship is mathematically secure before the final day. The championship is mathematically secure up to a tie on day `d` if one wrestler has at least as many wins as the other wrestlers have bouts remaining (change "at least" to "strictly more" to eliminate ties).

The best possible score wrestler `i` can have after day `d` is `s[i][d] + sum_{d < e <= D} sum_{0 <= j < i} f[j][i][e] + sum_{i < j < N} f[i][j][e]`
(assuming `i` wins all his remaining bouts).
Thus to specify that the championship is mathematically secure up to a tie for wrestler `i` with score `S` on day `d`,
we add a constraint that for all `0 <= k < N` where `k != i`, `S >= s[k][d] + sum{d < e <= D} (sum_{0 <= j < k} f[j][k][e] + sum_{k < j < N} f[k][j][e])`
(add `+ 1` to the left-hand-side to exclude ties).

#### Optimizing for Scores

A few queries examine how we can maximize or minimize the number of wrestlers with a specific score
(a special case of which is modeling the largest ties, which simply requires fixing the champion's score too).
We can give this as an optimization objective to the solver by defining variables
that encode whether a value is strictly less than a constant.

Based on [this Stack Exchange question](https://cs.stackexchange.com/questions/51025/cast-to-boolean-for-integer-linear-programming),
we can use this encoding to define a binary variable `l` such that `l` is 1 iff an integer value `a` is strictly less than a constant `C`.
Let us additionally assume that `0 <= a <= U` for some upper bound `U`.
We can enforce this with two constraints: `a - C <= (1-l)*(U+1) - 1` and `-l*(U+1) <= a - C`.
To verify this, let us consider the three possible cases: `a > C`, `a = C`, and `a < C`.
If `a > C`, then we get a contradiction if `l = 1`: `a - C <= -1`, but the constraints hold if `l = 0`.
If `a = C`, then `a - C = 0` and we get the same contradiction if `l = 1`, but the constraints hold if `l = 0`.
If `a < C`, then we get a contradicition if `l = 0`: `0 <= a - C`. The constraints hold if `l = 1`.
Thus, let us use the notation `lt(a, C, U)` to define such a variable with these constraints.

To maximize the number of wrestlers at least a specific score `S` on day `0 <= d < D`,
we add variables `l[i] = lt(s[i][d], S, M)` for all `0 <= i < N`. 
Since `l[i]` is 1 iff `s[i][d] < S`, then `1 - l[i]` is 1 iff `s[i][d] >= S`.
Thus, we set the solver objective to be `maximize sum_{0 <= i < N} (1 - l[i])`
to maximize the number of wrestlers with a score of at least `S` (analogously for minimizing).

To optimize for the largest tie, we specify that the champion have a particular score
and maximize the number of wrestlers with a score greater than or equal to that
(since they are already constrained to have less than or equal to the champion's score,
this will maximize the number exactly equal to the champion's score).

Similarly, we can optimize for the number of wrestlers with exactly a specific score `S` on day `d`
by maximizing or minimizing the sum of all `(1 - lt(s[i][d], S, M)) + lt(s[i][d], S+1, M)`
over all `0 <= i < N`, since `1 - lt(s[i][d], S, M)` is 1 iff `s[i][d] >= S`
and `lt(s[i][d], S+1, M)` is 1 iff `s[i][d] < S + 1`, i.e., `s[i][d] <= S`.

## Queries of Interest (to me)

### A sumo round-robin tournament

As mentioned in the introduction, I was curious as to how one would schedule a round-robin tournament while still meeting the requirements that each wrestler fight once a day and never face the same opponent more than once. As there are 42 top-division wrestlers, each
wrestler has 41 possible opponents, so such a round-robin tournament must be 41 days long (what a gauntlet).

I used the following query (omitting wins and losses because they're not necessary for the question and make the encoding larger):
`python sumo_query.py -k 0 -D 41 -M 41 --time 1200 --names names_files/makuuchi_11_2020.json generate`. I omitted the conflicts file because this would prevent certain matchups and it would likely be impossible to schedule it while still meeting the "each wrestler fights exactly once each day" requirement in the top division (without visitors from the second division).

I include the resulting schedule [here](schedules/round_robin.md), which took 567 seconds to solve.

Fun fact: Setting `-k` to 3 (constraining the final 3 fights on the final day to be between the top-rankers)
caused the solver to sputter. It did not find a solution within an hour and I was not willing to wait.

### Lowest outright winning score (no ties): 9-6

If I recall correctly, the lowest winning score in any real top-division tournament has been 11-4,
with Harumafuji being the last to achieve it in his final tournament in September 2017.
As we see below, the lowest possible winning score is 8-7, with a playoff, 
but I was also curious what the lowest winning score without a playoff would be.

While there are very many hard fighters in the current top division, 
I think Takayasu should have the honor of being the hypothetical champion in this situation,
since he has not yet (as of Nov. 2020) won a championship despite having been an ozeki and having been second place many times.

Query: `python sumo_query.py --names names_files/makuuchi_11_2020.json --conflicts conflicts_files/makuuchi_11_2020.json champ --idx 8 --score 9 --no-ties`

I include the resulting schedule [here](schedules/champ_with_9.md), which took 105 seconds to solve. Amusingly it includes a perfect opening week from Hakuho.

### Biggest tie with an 8-7 championship: 39 wrestlers

We can conclude that at least one wrestler must have a winning score, since if every wrestler had 7 or fewer wins
at the end of a 15-day tournament with 21 bouts a day, the total number of wins would be at most `42*7` while
the total number of bouts is `15*21`. However, it is possible for no wrestler to have more than the just the minimum winning score,
8-7.

I used the following query to try to optimize for the biggest tie with an 8-7 championship score: `python sumo_query.py --names names_files/makuuchi_11_2020.json --conflicts conflicts_files/makuuchi_11_2020.json --time 1200 champ --score 8 --max-tie`

I include the resulting schedule [here](schedules/champ_with_8.md), which took 870 seconds to solve.

All but 3 wrestlers ended up tied for the lead. I imagine the rankings committee would have an easy time later: Keep almost everyone in their current ranks, except for the unlucky saps (one's an ozeki and so would only be kadoban). The PR officials might have a harder time.

### Biggest tie with a 15-0 score: 21

Championships with perfect scores are very uncommon and I do not know if there has ever been a playoff between 15-0 wrestlers (I didn't check),
so I was curious to see how many wrestlers could simultaneously attain a perfect score over 15 days.
I felt silly when the solver finished, because this one isn't hard to work out on paper:
Pick half the division to win all their bouts, and other half to lose all their bouts,
and bounce all the losers between the winners for the 15 days, with the winners
never facing off until the monster playoff.

I used the following query to try to optimize for the biggest tie with 15-0 championship score: `python sumo_query.py --names names_files/makuuchi_11_2020.json --conflicts conflicts_files/makuuchi_11_2020.json --time 1200 champ --score 15 --max-tie`

I include the resulting schedule [here](schedules/most_perfect.md), which took 921 seconds to solve.

### All 42 wrestlers at 7-7 on day 14

The bloggers at [Tachiai.org](https://tachiai.org/) like to use the term "Darwin bout" to refer to bouts between 
wresters who both have a 7-7 record on the final day, since an 8-7 final score means a promotion while a 7-8 score
means a demotion. I was too lazy to specifically maximize final day faceoffs between 7-7 wrestlers,
but I did optimize for having the most wrestlers at 7-7 after day 14, whose fates would be determined by their final-day performance.
As it happens, _every_ bout on this day 15 is a Darwin bout. (Maybe I should have been able to figure this out on paper too.)

Query: `python sumo_query.py --names names_files/makuuchi_11_2020.json --conflicts conflicts_files/makuuchi_11_2020.json --time 600 opt-score --max --lower-score 7 --upper-score 7 --day 13`

I include the schedule [here](schedules/max_tension.md), which took 366 seconds of solver time.

### Most winning scores: 39 of 42

This query is slightly semantically different from seeking the maximal tie with an 8-7 championship, but the result was largely the same.

Query: `python sumo_query.py --names names_files/makuuchi_11_2020.json --conflicts conflicts_files/makuuchi_11_2020.json --time 1200 opt-score --max --lower-score 8 --upper-score 15 --day 14`

I include the schedule [here](schedules/most_winning.md), which took over 2000 seconds of solver time (yes, it didn't follow the time limit I set). The solver warns it cannot guarantee that this is optimal.

### Most losing scores: 39 of 42

I wonder what sort of reception this tournament would have.

Query: `python sumo_query.py --names names_files/makuuchi_11_2020.json --conflicts conflicts_files/makuuchi_11_2020.json --time 600 opt-score --max --lower-score 0 --upper-score 7 --day 14`

I include the schedule [here](schedules/most_losing.md), which took 432 seconds of solver time.

### Mathematically secure championship (up to tie) on day 10

I suppose a very early mathematically secure championship would be somewhat boring since the tension would be removed from much of the tournament, but a lot of people would have to be losing matches they would be expected to win to make that possible, which would surely also make for an exciting tournament.

I gave the hypothetical honor of this championship to Terunofuji, whose comeback to the top division has been utterly miraculous.

Query: `python sumo_query.py --names names_files/makuuchi_11_2020.json --conflicts conflicts_files/makuuchi_11_2020.json --time 600 champ --score 15 --secure 9 --idx 7`

I include the schedule [here](schedules/secure_tie_10.md), which took 42 seconds of solver time. Note that the constraints only required that the championship _be secure_ up to a tie on day 10: they did not require a tie to actually happen.

### Mathematically secure championship (excluding ties) on day 11

Who but Hakuho could have this one?

Query: `python sumo_query.py --names names_files/makuuchi_11_2020.json --conflicts conflicts_files/makuuchi_11_2020.json --time 600 champ --score 15 --secure 10 --no-ties`

I include the schedule [here](schedules/secure_outright_11.md), which took 83 seconds of solver time.

### Mathematically secure championship (up to tie) on day 9: Infeasible!

I used the following query: `python sumo_query.py -k 0 --time 600 champ --score 15 --secure 8`
and, after about 180 seconds, the solver concluded that the linear reduction of the integer linear program
was infeasible. So day 10 seems to be the earliest that the championship can be mathematically secure up to a tie.

### Mathematically secure championship (excluding ties) on day 10: Infeasible!

I used the following query: `python sumo_query.py -k 0 --time 600 champ --score 15 --secure 9 --no-ties`.
After only about 14 seconds, the solver concluded that the linear reduction was infeasible, so day 11
seems to be the earliest that the championship can be secured outright.

## Analytic Solution for Round-Robin Schedule when `N = 2^n`

Suppose we have `2^n` items that we want to group into `(2^n)-1` groups
where each group contains `2^(n-1)` pairs of items, each item appears in each group exactly once,
and each pair appears exactly once across the groups.
Let's call this procedure `schedule(items)` and define it inductively.

If `n` is 1, then we have exactly 2 items. There is only one pair that can be formed between them, so return it.

Now suppose that if we call `schedule()` on a list of `2^(n-1)` items, it will return `(2^(n-1))-1` groups of pairs of items
where each item appears in each group exactly once.

Suppose we have a list of `2^n` items where `n > 1`. We can group the pairs into `(2^n)-1` groups as follows:
First, split the list down the middle into two columns of `2^(n-1)` items each (we'll call these a "left column" and "right column").
Put the two columns next to each other, pairing the first item of the left column with the first item of the right column and so on.
This is one group of pairs. 

Notice that if we "rotate" the right column (move the first item to the second position, etc, 
moving the last item to the first position) while keeping the left column in place, we produce another group of `2^(n-1)` pairs with all the items appearing exactly once. After the initial columns, we can perform `(2^(n-1))-1` rotations before returning to the initial position: each of these rotations produces a distinct group of pairs where none of the pairs appeared in any prior rotation and each item appears exactly once in each group. Thus, counting the initial split, we have a total of `2^(n-1)` groups that represent all pairings between the two columns.

Now, let us consider pairings _within_ each column. We can take the columns of `2^(n-1)` items 
and call `schedule()` on those columns to produce `(2^(n-1))-1` groupings of all possible pairs of those items.
Let us then call `schedule()` on the left column to produce groups of pairs for the left column (we will call these the "left groups") and `schedule()` on the right column to produce pairs for the right column (we will call these the "right groups").
Each grouping among the left groups contains every item from the left column and each grouping among the right groups contains every item from the right column.
Thus, if we concatenate a left group with a right group, 
we will have a group containing every item from the original list, each appearing exactly once.

Thus we can produce another `(2^(n-1))-1` groups for the original list by concatenating 
the first left group to the first right group, the second left group to the second right group, 
and so on.
Combined with the `2^(n-1)` groups produced by the above rotation procedure, we now have a total of `(2^n)-1` groups. &#8718;

I would really like to generalize this proof!

We can implement this procedure in Python as follows:
```python
def schedule(items):
    if len(items) == 0:
        return []
    assert len(items) % 2 == 0, "You should only call this with a power of two"
    if len(items) == 2:
        return [[(items[0], items[1])]]
    
    left_column = [items[2*i] for i in range(len(items)//2)]
    right_column = [items[2*i+1] for i in range(len(items)//2)]
    assert len(left_column) == len(right_column)

    def rotate(col):
        last = col[-1]
        for i in range(len(col)):
            col[i], last = last, col[i]

    def combine_cols(col1, col2):
        return [(col1[i], col2[i]) for i in range(len(col1))]

    rotations = [combine_cols(left_column, right_column)]
    for i in range(len(right_column) - 1):
        rotate(right_column)
        rotations.append(combine_cols(left_column, right_column))

    left_groups = schedule(left_column)
    right_groups = schedule(right_column)
    assert len(left_groups) == len(right_groups)
    concat = [left_groups[i] + right_groups[i] for i in range(len(left_groups))]
    return rotations + concat
```
