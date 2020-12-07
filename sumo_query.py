import argparse
import json
import os
import sys

import mip
from mip import Model, BINARY, INTEGER

class TournamentParams:
    """
    Intended to collect some constants to describe tournament parameters.
    N: Number of wrestlers in the tournament
    D: Number of days in the tournametn
    B: Upper bound of bouts per day
    M: Number of bouts per wrestler per tournament

    Real sumo tournaments are 15 days long.
    In the top division there are 42 wrestlers and 21 bouts per day,
    and wrestler fighting 15 bouts per tournament.
    In the second division, there are 28 wrestlers and 14 bouts per day, 
    each wrestler fighting 15 bouts per tournament.
    In the third division, there are 120 wrestlers and 20-30 bouts per day,
    each wrestler fighting 7 bouts per tournament.

    Defaults correspond to the top division.
    """
    def __init__(self, N=42, D=15, LB=21, UB=21, M=15):
        self.N = N   # number of wrestlers
        self.D = D   # number of days in the tournament
        self.LB = LB # lower bound of bouts per day
        self.UB = UB # upper bound of bouts per day
        self.M = M   # number of matches per wrestler in the tournament

        # some validation, perhaps not all the criteria but enough to be useful
        assert N % 2 == 0, "Must have an even number of wrestlers"
        assert LB <= N//2, "Too many bouts for the number of wrestlers"
        # N choose 2 total pairs = (1/2)*N*N-1 total matchups
        assert LB*D <= (N*(N-1))//2, "More bouts scheduled than the number of valid matchups"

    # for convenience
    def astuple(self):
        return self.N, self.D, self.LB, self.UB, self.M


def print_assignment(match_assignments, match_victors=None, scores=None, name_subst=None, use_unicode=True, params=None):
    """
    A bit messy but this prints a markdown-formatted match schedule given a set of assignments
    in the form of a dictionary mapping (i, j) -> d where i is in [0, N), j is in [i+1, N),
    and d corresponds to the day of the matchup (i, j)

    Optionally, to have scores and match winners indicated, you can include
    a dictionary of match victors, mapping (i, j) -> True if i won or False if j won
    and scores, where scores[i][d] is the score of i on day d.

    To include wrestlers' names in the printout (in the same format as the official torikumi),
    you can pass an array of the following layout:
    name_subst[i] = [name (str), rank (str), is east side? (bool)]
    """
    if params is None:
        params = TournamentParams()
    N, D, _, _, M = params.astuple()

    def get_name(i):
        if name_subst is None:
            return f'R{i}'
        name = name_subst[i][0]
        rank = name_subst[i][1]
        side = 'E' if name_subst[i][2] else 'W'
        return f'{rank}{side} {name}'

    matches_by_day = {}
    for (matchup, day) in match_assignments.items():
        if day not in matches_by_day:
            matches_by_day[day] = []
        matches_by_day[day].append(matchup)

    if match_victors:
        losses = [[0 for d in range(D)] for i in range(N)]
        for d in range(D):
            for (i, j) in matches_by_day[d]:
                losses[i][d] = int(not match_victors[(i, j)])
                losses[j][d] = int(match_victors[i, j])
        defeats_by_day = [
            [ sum(losses[i][:d+1]) for d in range(D) ]
            for i in range(N)
        ]

    # the torikumi list the top-ranked matches last,
    # so we'll sort in reverse by index of the first wrestler
    for d in range(D):
        matches_by_day[d].sort(key=lambda match: -match[0])

    def win_marks(i, j):
        if not match_victors:
            return ' ', ' '
        left_wins = match_victors[(i, j)]
        win_star = '&#9675;' if use_unicode else '*'
        lose_star = '&#9679;' if use_unicode else 'o'
        if left_wins:
            return f' {win_star} ', f' {lose_star} '
        return f' {lose_star} ', f' {win_star} '

    def score_indicator(i, day):
        if scores is None:
            return ''

        score_str = f'({scores[i][day]} - {defeats_by_day[i][day]})'
        # emphasize a winning score
        if scores[i][day] > M//2:
            score_str = f'_{score_str}_'
        return score_str

    def is_east_side(i):
        if name_subst is None:
            return i % 2 == 0
        return name_subst[i][2]

    for day in range(D):
        print(f'# Matchups for Day {day+1}')
        print('| East | West |')
        print('|------|------|')
        for (i, j) in matches_by_day[day]:
            i_win_mark, j_win_mark = win_marks(i, j)
            i_score = score_indicator(i, day)
            j_score = score_indicator(j, day)

            east_fields = (get_name(i), i_score, i_win_mark)
            west_fields = (get_name(j), j_score, j_win_mark)

            # Assume even number => east side.
            # If both are even or both odd, then treat higher number as west side.
            # We only care about the case of j being on the east side and i on the west,
            # as this would reverse the initial ordering.
            if is_east_side(j) and not is_east_side(i):
                east_fields, west_fields = west_fields, east_fields

            print(f'| {east_fields[2]} {east_fields[0]} {east_fields[1]} | {west_fields[0]} {west_fields[1]} {west_fields[2]} |')
        print()

    if scores:
        max_score = max([scores[i][D-1] for i in range(N)])
        second_place = max([scores[i][D-1] for i in range(N) if scores[i][D-1] != max_score])

        winners = [i for i in range(N) if scores[i][D-1] == max_score]
        runners_up = [i for i in range(N) if scores[i][D-1] == second_place]

        title = 'Winner' if len(winners) == 1 else 'Playoff'
        print(f'## {title}')
        print(', '.join(map(get_name, winners)))

        # if there's multiple winners, then only the playoff losers are runners-up
        if len(winners) == 1:
            print('## Runner(s)-Up')
            print(', '.join(map(get_name, runners_up)))


def add_lt_constant_constraint(m, a, C, U):
    """
    Given a model m, an integer variable a, a constant C,
    and a constant U such that a <= U and C <= U
    returns a variable l such that l is 1 iff a < C
    """
    l = m.add_var(var_type=BINARY)

    # constraints:
    # 1. a - C <= (1 - l)*(U+1) - 1 (if l is 1, a - C <= -1 so a < C)
    # 2. -l*(U+1) <= a - C (if l is 0, then 0 <= a - C so a >= C)
    # If a > C, then a - C >= 0 so l=1 gives us a - C <= -1 (fails) but l=0 gives us a - C <= U and a - C >= 0 (both true)
    # If a = C, then a - C = 0 so l=1 gives us a - C <= -1 (fails) while l=0 gives us a - C <= U and a - C >= 0 (both true)
    # If a < C, then a - C < 0, so l=0 gives us a - C >= 0 (fails) while l=1 gives us a - C <= -1 and a - C >= -U (both true)
    m += (a - C <= (1-l)*(U+1) - 1)
    m += (-l*(U+1) <= a - C)
    return l


def set_up_fight_vars(params=None):
    """
    Creates a new ILP model and sets up constraints corresponding to
    valid matchups across the specified number of days

    Returns the model and a dictionary f such that f[i][j][d]
    is a binary var that is 1 iff i fights j on day d

    Constraints:
    Each wrestler fights at most once a day:
        for all i<N and d<D, sum_{j < i} f_{j, i, d} + f_{N > j > i} f_{i, j, d} <= 1
    Each matchup between wrestlers happens at most once:
        for all i<N and all j>i, sum_{d < days} f_{i, j, d} <= 1
    At most UB bouts are scheduled for each day:
        for all d<D, sum_{i<N} sum_{i<j<N} f_{i, j, d} <= UB
    At least LB bouts are scheduleed for each day:
        for all d<D, sum_{i<N} sum_{i<j<N} f_{i, j, d} >= LB
    Each wrestler fights M total bouts in a tournament:
        for all i<N, sum_{d < D} sum_{j < i} f_{j, i, d} + sum_{N > j > i} f_{i, j, d} == M
    """
    if params is None:
        params = TournamentParams()

    N, D, LB, UB, M = params.astuple()

    m = Model()
    m.emphasis = mip.SearchEmphasis.FEASIBILITY

    fight_vars = {
        i: {
            j: {
                d: m.add_var(name=f'f_{{{i}, {j}, {d}}}', var_type=BINARY)
                for d in range(D)
            }
            for j in range(i+1, N)
        }
        for i in range(N)
    }

    for i in range(N):
        for d in range(D):
            m += (mip.xsum([fight_vars[j][i][d] for j in range(i)]) + mip.xsum([fight_vars[i][j][d] for j in range(i+1, N)])) <= 1
        for j in range(i+1, N):
            m += mip.xsum([fight_vars[i][j][d] for d in range(D)]) <= 1
    
    for d in range(D):
        all_day_bouts = []
        for i in range(N):
            all_day_bouts += [fight_vars[i][j][d] for j in range(i+1, N)]
        m += (mip.xsum(all_day_bouts) <= UB)
        m += (mip.xsum(all_day_bouts) >= LB)

    for i in range(N):
        all_wrestler_bouts = []
        for d in range(D):
            all_wrestler_bouts += [fight_vars[j][i][d] for j in range(i)] + [fight_vars[i][j][d] for j in range(i+1, N)]
        m += (mip.xsum(all_wrestler_bouts) == M)

    return m, fight_vars


def set_up_score_vars(m, fight_vars, params=None):
    """
    Given an ILP model m with fight vars (f) set up for the given number of days,
    adds vars and constraints corresponding to which wrestlers won particular fights
    and what their scores were across the tournament.

    Returns: m, win_vars, score_vars
      where win_vars is a dictionary w such that
        w[i][j][d] is a binary var that is 1 iff i defeated j on day d
        (if f[i][j][d] is 1 and w[i][j][d] is 0, then j defeated i on day d)
      and score_vars is a dictionary s such that
        s[i][d] is an integer var that is s's score on day d

    Constraints:
    A wrestler cannot win a bout that did not happen
        for all i<N, j>i, d<D, w[i][j][d] <= f[i][j][d]
    A wrestler's score is the sum of all his victories over the tournament
        for all i<N, s[i][0] = sum_{j<i} (f[j][i][0] - w[j][i][0]) + sum_{i<j<N} w[i][j][0]
        for all i<N and 1 <= d < D, s[i][d] = s[i][d-1] + sum_{j<i} (f[j][i][d] - w[j][i][d]) + sum_{i<j<N} w[i][j][d]

    (For the first term of the second rule, 
     note that j wins the fight (i, j) iff f[i][j][k] = 1 and w[i][j][k] = 0.
     In this case, f[i][j][k] - w[i][j][k] = 1
     If f[i][j][k] = 0, then w[i][j][k] is constrained to be 0 and the difference is 0.
     If f[i][j][k] = 1 and w[i][j][k] = 1, meaning i won, the difference is also 0.)
    """
    if params is None:
        params = TournamentParams()
    N, D, _, _, _ = params.astuple()

    win_vars = {
        i: {
            j: {
                d: m.add_var(name=f'w_{{{i}, {j}, {d}}}', var_type=BINARY)
                for d in range(D)
            }
            for j in range(i+1, N)
        }
        for i in range(N)
    }

    score_vars = {
        i: {
            d: m.add_var(name=f's_{{{i}, {d}}}', var_type=INTEGER)
            for d in range(D)
        }
        for i in range(N)
    }

    # possible win constraints
    for i in range(N):
        for j in range(i+1, N):
            for d in range(D):
                m += win_vars[i][j][d] <= fight_vars[i][j][d]

    # score constraints
    for i in range(N):
        for d in range(D):
            win_vars_so_far = []
            for j in range(i):
                win_vars_so_far.append((fight_vars[j][i][d]-win_vars[j][i][d]))
            for j in range(i+1, N):
                win_vars_so_far.append(win_vars[i][j][d])

            total_wins = mip.xsum(win_vars_so_far)
            if d > 0:
                total_wins = total_wins + score_vars[i][d-1]
            m += (score_vars[i][d] == total_wins)

    return m, win_vars, score_vars


def specify_disallowed_matchups(m, disallowed_matchups, fight_vars, params=None):
    """
    Just for fun, if disallowed matchups (stablemates or close relatives) have been specified,
    this will add constraints preventing those fights from happening.

    Takes a model m with fight_vars (f) specified such that f[i][j][d] means that i faces j on day d,
    where d < D and a list of disallowed matchups (i, j), with the invariant that j>i.

    This may prevent some schedules from being feasible.

    Constraints:
    for each (i, j) in disallowed_matchups, for all d<days, f[i][j][d] = 0
    """
    if params is None:
        params = TournamentParams()

    for (i, j) in disallowed_matchups:
        for d in range(params.D):
            m += (fight_vars[i][j][d] == 0)
    return m


def specify_koreyori_sanyaku(m, reserved_matches, disallowed_matchups, fight_vars, params=None):
    """
    Just for fun, this will enforce the tradition that the last three matchups on the last day
    should be between the highest-ranking participants.

    In reality, the schedulers seem willing to bend this convention other than for
    yokozuna vs yokozuna matches, particularly if there are lower-ranked wrestlers
    who are challenging the top-rankers for the championship, so it is configurable
    how many of these top-ranked matches should be enforced.

    Warning: This may prevent some schedules from being feasible.
    """
    if params is None:
        params = TournamentParams()

    special_matches = []
    matched = set({})

    for i in range(params.N):
        if len(special_matches) == reserved_matches:
            break
        if i in matched:
            continue
        for j in range(i+1, params.N):
            if j in matched:
                continue
            if disallowed_matchups and (i, j) in disallowed_matchups:
                continue
            special_matches.append((i, j))
            matched.add(i)
            matched.add(j)
            break

    for (i, j) in special_matches:
        m += (fight_vars[i][j][params.D-1] == 1)
    return m


def parse_names(filename, params):
    if not filename:
        return None
    expand_name = os.path.abspath(os.path.expanduser(filename))
    with open(expand_name, 'r') as f:
        parsed = json.load(f)
    assert isinstance(parsed, list), 'Names file must be a list'
    assert len(parsed) == params.N, f'There must be {params.N} names, {len(parsed)} provided'
    def checker(item):
        if len(item) != 3:
            return False
        return isinstance(item[0], str) and isinstance(item[1], str) and isinstance(item[2], bool)
    assert all(map(checker, parsed)), 'Invalid entry in checker: Must be [name, rank, true if east else false]'
    return parsed


def parse_conflicts(filename, params):
    if not filename:
        return None
    expand_name = os.path.abspath(os.path.expanduser(filename))
    with open(expand_name, 'r') as f:
        parsed = json.load(f)
    assert isinstance(parsed, list), 'Conflicts file'
    assert len(parsed) == params.N, f'There must be {params.N} entries, {len(parsed)} provided'
    
    result = []
    for i in range(params.N):
        conflicts = parsed[i]
        for j in conflicts:
            assert isinstance(j, int), f'Entry {j} of conflicts entry for wrestler {i} is not an index'
            assert j > i, f'Entry {j} of conflicts for {i} is less than or equal to {i}'
            result.append((i, j))
    return result


def reject_invalid_solutions(solver_result):
    """
    Prints out an error message and exits if the solver did not find a solution.
    """
    if solver_result == mip.OptimizationStatus.OPTIMAL:
        # success
        return
    if solver_result == mip.OptimizationStatus.FEASIBLE:
        print('Warning: Solution not guaranteed optimal.')
        return
    if solver_result == mip.OptimizationStatus.NO_SOLUTION_FOUND:
        print('No schedule found: One may exist but the solver did not find it.')
        exit()
    if solver_result == mip.OptimizationStatus.INFEASIBLE or solver == mip.OptimizationStatus.INT_INFEASIBLE:
        print('Schedule impossible: Proven infeasible.')
        exit()
    if solver_result == mip.OptimizationStatus.LOADED:
        print('Query not loaded?')
        exit()
    if solver_result == mip.OptimizationStatus.ERROR:
        print('Solver internal error')
        exit()
    if solver_result == mip.OptimizationStatus.UNBOUNDED:
        print('Variable underconstrained and has optimal value at infinity?')
        exit()
    assert False, 'Unhandled optimization status'


def extract_match_assignments(fight_vars, params):
    match_assignments = {}
    N, D, _, _, _ = params.astuple()
    for i in range(N):
        for j in range(i+1, N):
            for d in range(D):
                if fight_vars[i][j][d].x > 0:
                    match_assignments[(i, j)] = d
                    break
    return match_assignments


def extract_victors_and_scores(fight_vars, win_vars, score_vars, params):
    N, D, _, _, _ = params.astuple()

    match_victors = {}
    for i in range(N):
        for j in range(i+1, N):
            for d in range(D):
                if fight_vars[i][j][d].x > 0:
                    match_victors[(i, j)] = bool(win_vars[i][j][d].x)
                    break
    scores = {}
    for i in range(N):
        scores[i] = {}
        for d in range(D):
            scores[i][d] = int(score_vars[i][d].x)
    return match_victors, scores


def generate_query(args):
    basic_query(args, include_scores=args.include_scores)


def champion_query(args):
    def champion_constraints(m, fight_vars, win_vars, score_vars, params):
        N, D, _, _, M = params.astuple()
        champ_score = args.score if args.score else M

        # the champion has at least the same score as everyone else on the last day
        for i in range(N):
            if i == args.idx:
                continue
            if args.no_ties:
                m += (score_vars[args.idx][D-1] >= score_vars[i][D-1] + 1)
            else:
                m += (score_vars[args.idx][D-1] >= score_vars[i][D-1])

        # Fix the champion's score if it's specified.
        # In principle, we could do without using a constant for the champ's score,
        #   but it makes maximizing ties much easier.
        m += (score_vars[args.idx][D-1] == champ_score)

        # if the championship is supposed to be mathematically secure on a certain day,
        # that means that on that day, the champion's score is greater than everyone else's
        # even if they win all their remaining bouts
        if args.secure:
            for i in range(N):
                if i == args.idx:
                    continue
                best_possible_score = [score_vars[i][args.secure]]
                for d in range(args.secure+1, D):
                    for j in range(i):
                        best_possible_score.append(fight_vars[j][i][d])
                    for j in range(i+1, N):
                        best_possible_score.append(fight_vars[i][j][d])
                if args.no_ties:
                    m += (score_vars[args.idx][args.secure] >= mip.xsum(best_possible_score) + 1)
                else:
                    m += (score_vars[args.idx][args.secure] >= mip.xsum(best_possible_score))

        if args.max_tie or args.min_tie:
            # if we have a variable l s.t. l is 1 iff i's score < the champion's score,
            # then (1-l) is 1 iff i's score >= the champion's score.
            # Since the wrestler's scores are already constrained to be <= the champion's scores,
            # maximizing (1-l) maximizes the number of _equal_ scores
            gte_flags = [
                (1-add_lt_constant_constraint(m, score_vars[i][D-1], champ_score, M))
                for i in range(N) if i != args.idx
            ]
            objective_func = mip.maximize if args.max_tie else mip.minimize
            m.objective = objective_func(mip.xsum(gte_flags))
        return m

    basic_query(args, include_scores=True, additional_constraints=champion_constraints)


def optimize_score_query(args):
    def score_constraints(m, fight_vars, win_vars, score_vars, params):
        N, D, _, _, M = params.astuple()
        day_to_meet = args.day if args.day else D-1

        # same principle as with optimizing ties
        gte_flags = [
            (1-add_lt_constant_constraint(m, score_vars[i][day_to_meet], args.lower_score, M))
            for i in range(N)
        ]
        # less than upper score + 1 -> less than or equal to upper score
        lt_flags = [
            add_lt_constant_constraint(m, score_vars[i][day_to_meet], args.upper_score+1, M)
            for i in range(N)
        ]
        if args.max:
            m.objective = mip.maximize(mip.xsum(gte_flags) + mip.xsum(lt_flags))
        if args.min:
            m.objective = mip.minimize(mip.xsum(gte_flags) + mip.xsum(lt_flags))
        return m

    basic_query(args, include_scores=True, additional_constraints=score_constraints)


def basic_query(args, include_scores=False, additional_constraints=None):
    params = TournamentParams(args.N, args.D, args.LB, args.UB, args.M)
    names = parse_names(args.names, params)
    conflicts = parse_conflicts(args.conflicts, params)

    m, fight_vars = set_up_fight_vars(params)
    win_vars, score_vars = None, None
    if include_scores:
        m, win_vars, score_vars = set_up_score_vars(m, fight_vars, params)
    if conflicts:
        m = specify_disallowed_matchups(m, conflicts, fight_vars, params)

    if args.koreyori_sanyaku:
        m = specify_koreyori_sanyaku(m, args.koreyori_sanyaku, conflicts, fight_vars, params)

    if additional_constraints:
        m = additional_constraints(m, fight_vars, win_vars, score_vars, params)

    res = m.optimize(max_seconds=args.time)
    reject_invalid_solutions(res)

    match_assignments = extract_match_assignments(fight_vars, params)
    match_victors, scores = None, None
    if include_scores:
        assert win_vars
        assert score_vars
        match_victors, scores = extract_victors_and_scores(fight_vars, win_vars, score_vars, params)

    print_assignment(match_assignments, match_victors=match_victors, scores=scores, name_subst=names, params=params)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Generate sumo tournament schedules with integer linear programming.')
    parser.add_argument('--N', type=int, help='Number of wrestlers in the division (must be even), default 42', default=42)
    parser.add_argument('--D', type=int, help='Number of tournament days, default 15', default=15)
    parser.add_argument('--LB', type=int, help='Minimum number of bouts per day, default 21', default=21)
    parser.add_argument('--UB', type=int, help='Maximum number of bouts per day, default 21', default=21)
    parser.add_argument('--M', type=int, help='Number of bouts each wrestler fights in a tournament, default 15', default=15)
    parser.add_argument('--time', type=int, help='Solver time (seconds), default 300', default=300)
    parser.add_argument('--names', type=str, required=False,
                        help='JSON file giving wrestler names, ranks, and side. Used for generating printouts.\n'
                             'File format: [\n    ["name for rikishi 0", "rank for rikishi 0", true if east rank false if west rank],\n    ...\n]')
    parser.add_argument('--conflicts', type=str, required=False,
                        help='JSON file specifying disallowed matchups due to being stablemates or blood relatives.\n'
                        'File format: [\n    [indices (> 0) of rikishi that rikishi #0 cannot fight],\n    [indices (> 1) of rikishi that rikishi #1 cannot fight],\n    ...\n]')
    parser.add_argument('-k', '--koreyori-sanyaku', type=int, default=1,
                        help='Just for fun, enforces the convention that the 3 final bouts on the final day be between top-rankers.\n'
                        'Fixes the final k matches on the final day to be between the k top-ranked pairings. (Default 1.)\nSet to 0 to disable.\n'
                        'The default is set to 1 because in practice the schedulers have been willing to bend this tradition except for yokozuna vs yokozuna matches.')

    subparsers = parser.add_subparsers(title='query',
                                       help='subcommends for generating tournaments',
                                       required=True)

    generator = subparsers.add_parser('generate', help='Just generates a tournament schedule with no objective')
    generator.add_argument('-i', '--include-scores', action='store_true', 
                           help='Include scores in the generated schedule? Doing so increases the number of variables and constraints.')
    generator.set_defaults(func=generate_query)

    champion = subparsers.add_parser('champ', help='Queries pertaining to the tournament champion')
    
    tie_options = champion.add_mutually_exclusive_group()
    tie_options.add_argument('--no-ties', action='store_true',
                             help='If set, there will only be a single champion, no playoff.')
    tie_options.add_argument('--max-tie', action='store_true',
                             help='If set, the solver will maximize the number of wrestlers tied for the championship.')
    tie_options.add_argument('--min-tie', action='store_true',
                             help='If set, the solver will minimize the number of wrestlers tied for the championship.')

    champion.add_argument('--idx', type=int, default=0, help='Gives a wrestler index to fix as the champion (or at least one)')
    champion.add_argument('--score', type=int, required=False, 
                          help='Specify the winning score for the champion (default: M)')
    champion.add_argument('--secure', type=int, required=False,
                          help='Specify by which day the championship is mathematically secure (0-based)')
    champion.set_defaults(func=champion_query)

    opt_score = subparsers.add_parser('opt-score', help='Maximimize or minimize the number of wrestlers a score in the given range (inclusive)')
    opt_score_flags = opt_score.add_mutually_exclusive_group(required=True)
    opt_score_flags.add_argument('--max', action='store_true')
    opt_score_flags.add_argument('--min', action='store_true')

    opt_score.add_argument('--lower-score', type=int, required=True, help='Minimum threshold for the score (inclusive)')
    opt_score.add_argument('--upper-score', type=int, required=True, help='Maximim threshold for the score (inclusive)')
    opt_score.add_argument('--day', type=int, required=False, help='The day (0-based) on which the criterion applies (default: D-1)')
    opt_score.set_defaults(func=optimize_score_query)

    args = parser.parse_args()
    args.func(args)
