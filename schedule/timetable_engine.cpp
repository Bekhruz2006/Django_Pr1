#include <algorithm>
#include <atomic>
#include <cassert>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <functional>
#include <iomanip>
#include <iostream>
#include <limits>
#include <map>
#include <memory>
#include <mutex>
#include <numeric>
#include <random>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <unordered_map>
#include <vector>

#include "json.hpp"
using json = nlohmann::json;
using namespace std;
using Clock = chrono::steady_clock;
using TP    = chrono::time_point<Clock>;

namespace SC {
    constexpr double UNPLACED          = -2000.0;
    constexpr double WRONG_LECTURE     =   -60.0;
    constexpr double WRONG_LAB         =   -60.0;
    constexpr double WRONG_PREF        =   -35.0;
    constexpr double OVERFLOW_FACTOR   =  -100.0;
    constexpr double TINY_ROOM         =   -25.0;
    constexpr double LATE_PER_IDX      =    -2.0;
    constexpr double ADJACENT_BONUS    =   +15.0;
    constexpr double EMPTY_DAY_BONUS   =    +5.0;
    constexpr double GAP_PENALTY       =   -30.0;
    constexpr double TEACHER_OVERLOAD  =   -20.0;
    constexpr double TEACHER_LOAD_PER  =    -8.0;
    constexpr double SPREAD_BONUS      =    +8.0;
    constexpr double CROWD_PENALTY     =   -12.0;
}

enum class WeekType   : int8_t { EVERY=0, RED=1, BLUE=2 };
enum class LessonType : int8_t { LECTURE=0, PRACTICE=1, LAB=2, SRSP=3 };
enum class RoomType   : int8_t {
    LECTURE=0, PRACTICE=1, COMPUTER=2, LAB=3,
    LINGUISTIC=4, SPORT=5, UNKNOWN=6
};

static WeekType wtFromStr(const string& s) {
    if (s=="RED")  return WeekType::RED;
    if (s=="BLUE") return WeekType::BLUE;
    return WeekType::EVERY;
}
static string wtToStr(WeekType w) {
    if (w==WeekType::RED)  return "RED";
    if (w==WeekType::BLUE) return "BLUE";
    return "EVERY";
}
static LessonType ltFromStr(const string& s) {
    if (s=="PRACTICE") return LessonType::PRACTICE;
    if (s=="LAB")      return LessonType::LAB;
    if (s=="SRSP")     return LessonType::SRSP;
    return LessonType::LECTURE;
}
static string ltToStr(LessonType lt) {
    if (lt==LessonType::PRACTICE) return "PRACTICE";
    if (lt==LessonType::LAB)      return "LAB";
    if (lt==LessonType::SRSP)     return "SRSP";
    return "LECTURE";
}
static RoomType rtFromStr(const string& s) {
    if (s=="PRACTICE")   return RoomType::PRACTICE;
    if (s=="COMPUTER")   return RoomType::COMPUTER;
    if (s=="LAB")        return RoomType::LAB;
    if (s=="LINGUISTIC") return RoomType::LINGUISTIC;
    if (s=="SPORT")      return RoomType::SPORT;
    if (s=="LECTURE")    return RoomType::LECTURE;
    return RoomType::UNKNOWN;
}

struct TSlot {
    int    id;
    string start;
    string end;
    int    number;
};

struct Room {
    int      id;
    string   number;
    int      capacity;
    RoomType room_type;
};

struct Task {
    int            id;
    int            subject_id;
    string         subject_name;
    int            teacher_id;      
    vector<int>    groups;          
    vector<int>    group_ids;       
    int            students;
    LessonType     ltype;
    bool           is_stream;
    int            stream_tag;
    RoomType       pref_room;
    WeekType       week_pref;
    bool           is_wt_flexible;
};

struct Placement {
    int8_t   day      = -1;
    int8_t   ts_idx   = -1;
    int16_t  room_idx = -1;
    WeekType wt       = WeekType::EVERY;

    bool placed() const { return room_idx >= 0; }
};

struct Problem {
    vector<TSlot>  slots;
    vector<Room>   rooms;
    vector<Task>   tasks;

    unordered_map<int,int> teacher_idx;
    int n_teachers = 0;

    unordered_map<int,int> group_idx;
    int n_groups = 0;

    unordered_map<int,int> room_idx_map;

    vector<vector<bool>> teacher_unavail;

    double sa_t0        = 1200.0;
    double sa_cooling   = 0.99985;
    double sa_reheat    = 1.5;
    int    sa_restarts  = 6;
    int    sa_steps     = 400000;
    int    max_seconds  = 90;

    int  overflow_mode     = 1;
    bool strict_room_types = false;
    bool avoid_gaps        = true;
    int  max_group_per_day   = 4;
    int  max_teacher_per_day = 4;

    int nDays()     const { return 6; }
    int nSlots()    const { return (int)slots.size(); }
    int nRooms()    const { return (int)rooms.size(); }
    int nTasks()    const { return (int)tasks.size(); }
    int nTeachers() const { return n_teachers; }
    int nGroups()   const { return n_groups; }
};

struct BusyMap {
    vector<int16_t> teacher_busy;
    vector<int16_t> group_busy;
    vector<int16_t> room_busy;
    vector<int16_t> teacher_day_cnt;
    vector<int16_t> group_day_cnt;

    int n_teachers, n_groups, n_rooms, n_days, n_slots;
    int stride_te, stride_td;
    int stride_ge, stride_gd;
    int stride_re, stride_rd;

    void init(int nt, int ng, int nr, int nd, int ns) {
        n_teachers=nt; n_groups=ng; n_rooms=nr; n_days=nd; n_slots=ns;
        stride_td = ns * 2;  stride_te = nd * stride_td;
        stride_gd = ns * 2;  stride_ge = nd * stride_gd;
        stride_rd = ns * 2;  stride_re = nd * stride_rd;
        teacher_busy   .assign(nt * stride_te, 0);
        group_busy     .assign(ng * stride_ge, 0);
        room_busy      .assign(nr * stride_re, 0);
        teacher_day_cnt.assign(nt * nd, 0);
        group_day_cnt  .assign(ng * nd, 0);
    }

    static inline bool isBusy(const int16_t* v, int off, WeekType wt) {
        switch (wt) {
            case WeekType::EVERY: return (v[off] | v[off+1]) > 0;
            case WeekType::RED:   return v[off]   > 0;
            case WeekType::BLUE:  return v[off+1] > 0;
        }
        return false;
    }
    static inline void modify(int16_t* v, int off, WeekType wt, int d) {
        if (wt == WeekType::EVERY || wt == WeekType::RED)  v[off]   += (int16_t)d;
        if (wt == WeekType::EVERY || wt == WeekType::BLUE) v[off+1] += (int16_t)d;
    }

    bool hasConflict(const Problem& pb, const Task& task,
                     int day, int tsi, int ri, WeekType wt) const
    {
        if (task.teacher_id >= 0) {
            auto it = pb.teacher_idx.find(task.teacher_id);
            if (it != pb.teacher_idx.end()) {
                int tl = it->second;
                int ui = day * n_slots + tsi;
                if (ui < (int)pb.teacher_unavail[tl].size() &&
                    pb.teacher_unavail[tl][ui]) return true;
                int off = tl * stride_te + day * stride_td + tsi * 2;
                if (isBusy(teacher_busy.data(), off, wt)) return true;
            }
        }
        for (int gl : task.groups) {
            int off = gl * stride_ge + day * stride_gd + tsi * 2;
            if (isBusy(group_busy.data(), off, wt)) return true;
        }
        {
            int off = ri * stride_re + day * stride_rd + tsi * 2;
            if (isBusy(room_busy.data(), off, wt)) return true;
        }
        return false;
    }

    void apply(const Problem& pb, const Task& task,
               int day, int tsi, int ri, WeekType wt, int delta)
    {
        if (task.teacher_id >= 0) {
            auto it = pb.teacher_idx.find(task.teacher_id);
            if (it != pb.teacher_idx.end()) {
                int tl  = it->second;
                int off = tl * stride_te + day * stride_td + tsi * 2;
                modify(teacher_busy.data(), off, wt, delta);
                teacher_day_cnt[tl * n_days + day] += (int16_t)delta;
            }
        }
        for (int gl : task.groups) {
            int off = gl * stride_ge + day * stride_gd + tsi * 2;
            modify(group_busy.data(), off, wt, delta);
            group_day_cnt[gl * n_days + day] += (int16_t)delta;
        }
        {
            int off = ri * stride_re + day * stride_rd + tsi * 2;
            modify(room_busy.data(), off, wt, delta);
        }
    }

    bool groupHasClassAt(int gl, int day, int tsi, WeekType wt) const {
        int off = gl * stride_ge + day * stride_gd + tsi * 2;
        return isBusy(group_busy.data(), off, wt);
    }
    int teacherDayCount(int tl, int day) const {
        return teacher_day_cnt[tl * n_days + day];
    }
    int groupDayCount(int gl, int day) const {
        return group_day_cnt[gl * n_days + day];
    }
};

template<typename T>
static T jget(const json& j, const char* key, T dflt) {
    const json* p = j.find_ptr(key);
    if (!p || p->is_null()) return dflt;
    try { return p->get<T>(); } catch(...) { return dflt; }
}

static bool roomIsCompatible(const Problem& pb, const Task& task, const Room& room) {
    if (!pb.strict_room_types) return true;
    if (task.ltype == LessonType::LECTURE)
        return room.room_type == RoomType::LECTURE || room.room_type == RoomType::SPORT;
    if (task.ltype == LessonType::LAB)
        return room.room_type == RoomType::LAB;
    if (task.pref_room != RoomType::UNKNOWN)
        return room.room_type == task.pref_room;
    return true;
}

static bool capacityOk(const Problem& pb, const Task& task, const Room& room) {
    double ratio = (double)task.students / max(1, room.capacity);
    switch (pb.overflow_mode) {
        case 0: return ratio <= 1.00;
        case 1: return ratio <= 1.25;
        case 2: return ratio <= 1.50;
        default: return ratio <= 1.50;
    }
}

static double roomTypePenalty(const Problem& pb, const Task& task, const Room& room) {
    if (pb.strict_room_types) {
        return 0.0;
    }
    double pen = 0.0;
    if (task.ltype == LessonType::LECTURE &&
        room.room_type != RoomType::LECTURE &&
        room.room_type != RoomType::SPORT)
        pen += SC::WRONG_LECTURE;
    if (task.ltype == LessonType::LAB && room.room_type != RoomType::LAB)
        pen += SC::WRONG_LAB;
    if (task.pref_room != RoomType::UNKNOWN && room.room_type != task.pref_room)
        pen += SC::WRONG_PREF;
    return pen;
}

static double capacityPenalty(const Task& task, const Room& room) {
    double ratio = (double)task.students / max(1, room.capacity);
    if (ratio > 1.0)  return SC::OVERFLOW_FACTOR * (ratio - 1.0);
    if (ratio < 0.30) return SC::TINY_ROOM;
    return 0.0;
}

static double gapScore(const BusyMap& bm, const Problem& pb,
                       const Task& task, int day, int tsi, WeekType wt)
{
    if (!pb.avoid_gaps) return 0.0;
    double score = 0.0;
    int ns = pb.nSlots();

    for (int gl : task.groups) {
        bool has_prev = (tsi > 0)    && bm.groupHasClassAt(gl, day, tsi-1, wt);
        bool has_next = (tsi < ns-1) && bm.groupHasClassAt(gl, day, tsi+1, wt);

        if (has_prev || has_next) {
            score += SC::ADJACENT_BONUS;
        } else {
            bool day_empty = true;
            for (int s = 0; s < ns && day_empty; s++)
                if (bm.groupHasClassAt(gl, day, s, wt)) day_empty = false;

            score += day_empty ? SC::EMPTY_DAY_BONUS : SC::GAP_PENALTY;
        }
    }
    return score;
}

static double spreadScore(const BusyMap& bm, const Problem& pb,
                          const Task& task, int day)
{
    double score = 0.0;
    for (int gl : task.groups) {
        int cnt = bm.groupDayCount(gl, day);
        if (cnt == 0)                    score += SC::SPREAD_BONUS;
        else if (cnt >= pb.max_group_per_day) score += SC::CROWD_PENALTY;
    }
    return score;
}

static double teacherBalanceScore(const BusyMap& bm, const Problem& pb,
                                  const Task& task, int day)
{
    if (task.teacher_id < 0) return 0.0;
    auto it = pb.teacher_idx.find(task.teacher_id);
    if (it == pb.teacher_idx.end()) return 0.0;
    int cnt = bm.teacherDayCount(it->second, day);
    if (cnt >= pb.max_teacher_per_day)
        return SC::TEACHER_OVERLOAD + SC::TEACHER_LOAD_PER * (cnt - pb.max_teacher_per_day + 1);
    return 0.0;
}

static double slotScore(const BusyMap& bm, const Problem& pb,
                        const Task& task,
                        int day, int tsi, int ri, WeekType wt)
{
    const Room& room = pb.rooms[ri];
    if (!roomIsCompatible(pb, task, room)) return SC::UNPLACED;
    if (!capacityOk(pb, task, room))       return SC::UNPLACED;

    double sc = 0.0;
    sc += capacityPenalty(task, room);
    sc += roomTypePenalty(pb, task, room);
    sc += gapScore(bm, pb, task, day, tsi, wt);
    sc += SC::LATE_PER_IDX * tsi;
    sc += spreadScore(bm, pb, task, day);
    sc += teacherBalanceScore(bm, pb, task, day);
    return sc;
}

static double fullScore(const Problem& pb, const vector<Placement>& sol) {
    if (sol.empty()) return SC::UNPLACED * pb.nTasks();
    BusyMap bm;
    bm.init(pb.nTeachers(), pb.nGroups(), pb.nRooms(), pb.nDays(), pb.nSlots());
    double sc = 0.0;
    for (int i = 0; i < (int)sol.size(); i++) {
        const Task&      task = pb.tasks[i];
        const Placement& p    = sol[i];
        if (!p.placed()) { sc += SC::UNPLACED; continue; }
        sc += slotScore(bm, pb, task, p.day, p.ts_idx, p.room_idx, p.wt);
        bm.apply(pb, task, p.day, p.ts_idx, p.room_idx, p.wt, +1);
    }
    return sc;
}

static Problem parseInput(const json& j) {
    Problem pb;

    pb.sa_t0        = jget<double>(j, "sa_t0",        pb.sa_t0);
    pb.sa_cooling   = jget<double>(j, "sa_cooling",   pb.sa_cooling);
    pb.sa_reheat    = jget<double>(j, "sa_reheat",    pb.sa_reheat);
    pb.sa_restarts  = jget<int>   (j, "sa_restarts",  pb.sa_restarts);
    pb.sa_steps     = jget<int>   (j, "sa_steps",     pb.sa_steps);
    pb.max_seconds  = jget<int>   (j, "max_seconds",  pb.max_seconds);

    pb.overflow_mode     = jget<int> (j, "overflow_mode",     pb.overflow_mode);
    pb.strict_room_types = jget<bool>(j, "strict_room_types", pb.strict_room_types);
    pb.avoid_gaps        = jget<bool>(j, "avoid_gaps",        pb.avoid_gaps);

    for (const auto& s : j.at("time_slots")) {
        TSlot ts;
        ts.id     = s.at("id").get<int>();
        ts.start  = jget<string>(s, "start_time", "08:00");
        ts.end    = jget<string>(s, "end_time",   "08:50");
        ts.number = jget<int>   (s, "number",     (int)pb.slots.size()+1);
        pb.slots.push_back(ts);
    }

    {
        int local = 0;
        for (const auto& r : j.at("rooms")) {
            Room room;
            room.id        = r.at("id").get<int>();
            room.number    = jget<string>(r, "number",    "?");
            room.capacity  = jget<int>   (r, "capacity",  30);
            room.room_type = rtFromStr(jget<string>(r, "room_type", "PRACTICE"));
            pb.room_idx_map[room.id] = local++;
            pb.rooms.push_back(room);
        }
    }

    for (const auto& g : j.at("groups")) {
        int gid = g.at("id").get<int>();
        if (!pb.group_idx.count(gid))
            pb.group_idx[gid] = pb.n_groups++;
    }

    for (const auto& t : j.at("tasks")) {
        int tid = jget<int>(t, "teacher_id", -1);
        if (tid >= 0 && !pb.teacher_idx.count(tid))
            pb.teacher_idx[tid] = pb.n_teachers++;
    }

    pb.teacher_unavail.assign(pb.n_teachers,
        vector<bool>(pb.nDays() * (int)pb.slots.size(), false));
    {
        unordered_map<int,int> slot_local;
        for (int i = 0; i < (int)pb.slots.size(); i++)
            slot_local[pb.slots[i].id] = i;

        const json* tunavail = j.find_ptr("teacher_unavailable");
        if (tunavail && !tunavail->is_null()) { const json& it = *tunavail;
            for (const auto& u : it) {
                int tid   = jget<int>(u, "teacher_id",   -1);
                int day   = jget<int>(u, "day_of_week",  -1);
                int ts_id = jget<int>(u, "time_slot_id", -1);
                if (tid<0 || day<0 || ts_id<0) continue;
                auto tit = pb.teacher_idx.find(tid);
                auto sit = slot_local.find(ts_id);
                if (tit==pb.teacher_idx.end() || sit==slot_local.end()) continue;
                int idx = day * (int)pb.slots.size() + sit->second;
                if (idx < (int)pb.teacher_unavail[tit->second].size())
                    pb.teacher_unavail[tit->second][idx] = true;
            }
        }
    }

    {
        int task_counter = 0;
        for (const auto& t : j.at("tasks")) {
            int    subject_id  = t.at("subject_id").get<int>();
            string subj_name   = jget<string>(t, "subject_name", "");
            int    teacher_id  = jget<int>(t, "teacher_id", -1);
            auto&  gids_json   = t.at("group_ids");
            bool   is_stream   = jget<bool>(t, "is_stream", false);
            int    stream_tag  = jget<int>(t, "stream_tag", -1);
            int    students    = jget<int>(t, "students", 25);
            LessonType lt      = ltFromStr(jget<string>(t, "lesson_type", "LECTURE"));
            RoomType pref_rt   = rtFromStr(jget<string>(t, "preferred_room_type", ""));
            double weekly_f    = jget<double>(t, "weekly_slots", 1.0);

            vector<int> grp_local, grp_db;
            for (const auto& gj : gids_json) {
                int gid = gj.get<int>();
                grp_db.push_back(gid);
                auto git = pb.group_idx.find(gid);
                if (git != pb.group_idx.end())
                    grp_local.push_back(git->second);
            }

            // Разворачивание
            if (weekly_f < 0.0) weekly_f = 0.0;
            int    every_count = (int)floor(weekly_f);
            double frac        = weekly_f - every_count;
            bool   need_biweek = (frac >= 0.10);

            if (every_count == 0 && !need_biweek && weekly_f > 0.01)
                need_biweek = true;

            auto makeTask = [&](WeekType wt, bool flexible) {
                Task tk;
                tk.id             = task_counter++;
                tk.subject_id     = subject_id;
                tk.subject_name   = subj_name;
                tk.teacher_id     = teacher_id;
                tk.groups         = grp_local;
                tk.group_ids      = grp_db;
                tk.students       = students;
                tk.ltype          = lt;
                tk.is_stream      = is_stream;
                tk.stream_tag     = stream_tag;
                tk.pref_room      = pref_rt;
                tk.week_pref      = wt;
                tk.is_wt_flexible = flexible;
                pb.tasks.push_back(tk);
            };

            for (int k = 0; k < every_count; k++)
                makeTask(WeekType::EVERY, false);

            if (need_biweek)
                makeTask(WeekType::RED, true);  
        }
    }

    return pb;
}
static vector<Placement> greedySeed(const Problem& pb,
                                    BusyMap& bm,
                                    mt19937& rng)
{
    int nT = pb.nTasks();
    int nR = pb.nRooms();
    int nS = pb.nSlots();
    int nD = pb.nDays();

    vector<Placement> sol(nT);

    vector<int> order(nT);
    iota(order.begin(), order.end(), 0);
    shuffle(order.begin(), order.end(), rng);
    stable_sort(order.begin(), order.end(), [&](int a, int b){
        const Task& ta = pb.tasks[a];
        const Task& tb = pb.tasks[b];
        if (ta.is_stream != tb.is_stream) return (int)ta.is_stream > (int)tb.is_stream;
        return ta.students > tb.students;
    });

    vector<int> room_order(nR);
    iota(room_order.begin(), room_order.end(), 0);
    shuffle(room_order.begin(), room_order.end(), rng);

    for (int ti : order) {
        const Task& task = pb.tasks[ti];

        vector<WeekType> wt_opts = task.is_wt_flexible
            ? vector<WeekType>{WeekType::RED, WeekType::BLUE}
            : vector<WeekType>{task.week_pref};

        double best_sc   = numeric_limits<double>::lowest();
        Placement best_p;

        for (WeekType wt : wt_opts) {
            for (int d = 0; d < nD; d++) {
                for (int s = 0; s < nS; s++) {
                    for (int ri : room_order) {
                        const Room& room = pb.rooms[ri];
                        if (!roomIsCompatible(pb, task, room)) continue;
                        if (!capacityOk(pb, task, room))       continue;
                        if (bm.hasConflict(pb, task, d, s, ri, wt)) continue;

                        double sc = slotScore(bm, pb, task, d, s, ri, wt);
                        if (sc > best_sc) {
                            best_sc = sc;
                            best_p  = {(int8_t)d, (int8_t)s, (int16_t)ri, wt};
                        }
                    }
                }
            }
        }

        if (best_sc > numeric_limits<double>::lowest()) {
            sol[ti] = best_p;
            bm.apply(pb, task, best_p.day, best_p.ts_idx,
                     best_p.room_idx, best_p.wt, +1);
        }
    }
    return sol;
}

struct MoveStats {
    int    trials = 0;
    double reward = 0.0;

    double ucb1(int total, double c = 1.5) const {
        if (trials == 0) return 1e9;
        return reward / trials + c * sqrt(log((double)(total + 1)) / trials);
    }
};

static vector<Placement> anneal(const Problem& pb,
                                vector<Placement> sol,
                                BusyMap bm,
                                mt19937& rng,
                                double T,
                                double cooling,
                                int steps,
                                TP deadline)
{
    const int nT = pb.nTasks();
    const int nR = pb.nRooms();
    const int nD = pb.nDays();
    const int nS = pb.nSlots();
    if (nT == 0 || nR == 0 || nS == 0) return sol;

    double cur_score  = fullScore(pb, sol);
    auto   best_sol   = sol;
    double best_score = cur_score;

    constexpr int N_MOVES = 8;
    array<MoveStats, N_MOVES> mst;
    int total_trials = 0;

    uniform_real_distribution<double> rU(0.0, 1.0);
    uniform_int_distribution<int> rTask(0, nT-1);
    uniform_int_distribution<int> rDay (0, nD-1);
    uniform_int_distribution<int> rSlot(0, nS-1);
    uniform_int_distribution<int> rRoom(0, nR-1);

    auto check = [&]() { return Clock::now() < deadline; };

    for (int step = 0; step < steps; step++) {
        if ((step & 0x7FF) == 0 && !check()) break;

        int mv;
        if (total_trials < N_MOVES * 3) {
            mv = total_trials % N_MOVES;
        } else {
            mv = 0;
            double best_u = mst[0].ucb1(total_trials);
            for (int m = 1; m < N_MOVES; m++) {
                double u = mst[m].ucb1(total_trials);
                if (u > best_u) { best_u = u; mv = m; }
            }
        }

        bool   accepted = false;
        double delta    = 0.0;

        if (mv == 0) {
            int i = rTask(rng);
            const Task& task = pb.tasks[i];
            Placement&  p    = sol[i];
            int nd  = rDay(rng), nts = rSlot(rng), nr = rRoom(rng);
            WeekType nwt = task.is_wt_flexible
                ? (rU(rng)<0.5 ? WeekType::RED : WeekType::BLUE)
                : task.week_pref;

            if (p.placed()) bm.apply(pb,task,p.day,p.ts_idx,p.room_idx,p.wt,-1);
            if (!bm.hasConflict(pb,task,nd,nts,nr,nwt)) {
                double os = p.placed()
                    ? slotScore(bm,pb,task,p.day,p.ts_idx,p.room_idx,p.wt)
                    : SC::UNPLACED;
                double ns2 = slotScore(bm,pb,task,nd,nts,nr,nwt);
                delta = ns2 - os;
                if (delta > 0.0 || rU(rng) < exp(delta / T)) {
                    bm.apply(pb,task,nd,nts,nr,nwt,+1);
                    p = {(int8_t)nd,(int8_t)nts,(int16_t)nr,nwt};
                    cur_score += delta; accepted = true;
                } else {
                    if (p.placed()) bm.apply(pb,task,p.day,p.ts_idx,p.room_idx,p.wt,+1);
                }
            } else {
                if (p.placed()) bm.apply(pb,task,p.day,p.ts_idx,p.room_idx,p.wt,+1);
            }

        } else if (mv == 1) {
            int i = rTask(rng), j = rTask(rng);
            if (i == j) goto upd;
            {
                const Task& ti = pb.tasks[i];  const Task& tj = pb.tasks[j];
                Placement   pi = sol[i];        Placement   pj = sol[j];
                if (!pi.placed() && !pj.placed()) goto upd;

                WeekType wti = ti.is_wt_flexible
                    ? (pj.placed()?pj.wt:(rU(rng)<0.5?WeekType::RED:WeekType::BLUE))
                    : ti.week_pref;
                WeekType wtj = tj.is_wt_flexible
                    ? (pi.placed()?pi.wt:(rU(rng)<0.5?WeekType::RED:WeekType::BLUE))
                    : tj.week_pref;

                if (pi.placed()) bm.apply(pb,ti,pi.day,pi.ts_idx,pi.room_idx,pi.wt,-1);
                if (pj.placed()) bm.apply(pb,tj,pj.day,pj.ts_idx,pj.room_idx,pj.wt,-1);

                double osi = pi.placed()?slotScore(bm,pb,ti,pi.day,pi.ts_idx,pi.room_idx,pi.wt):SC::UNPLACED;
                double osj = pj.placed()?slotScore(bm,pb,tj,pj.day,pj.ts_idx,pj.room_idx,pj.wt):SC::UNPLACED;

                bool oki=false, okj=false;
                double nsi=SC::UNPLACED, nsj=SC::UNPLACED;

                if (pj.placed() && !bm.hasConflict(pb,ti,pj.day,pj.ts_idx,pj.room_idx,wti)) {
                    nsi = slotScore(bm,pb,ti,pj.day,pj.ts_idx,pj.room_idx,wti);
                    oki = (nsi > -1e8);
                }
                if (oki) bm.apply(pb,ti,pj.day,pj.ts_idx,pj.room_idx,wti,+1);
                if (pi.placed() && !bm.hasConflict(pb,tj,pi.day,pi.ts_idx,pi.room_idx,wtj)) {
                    nsj = slotScore(bm,pb,tj,pi.day,pi.ts_idx,pi.room_idx,wtj);
                    okj = (nsj > -1e8);
                }
                if (oki) bm.apply(pb,ti,pj.day,pj.ts_idx,pj.room_idx,wti,-1);

                delta = (nsi - osi) + (nsj - osj);
                if (oki && okj && (delta > 0.0 || rU(rng) < exp(delta/T))) {
                    if (pj.placed()) bm.apply(pb,ti,pj.day,pj.ts_idx,pj.room_idx,wti,+1);
                    if (pi.placed()) bm.apply(pb,tj,pi.day,pi.ts_idx,pi.room_idx,wtj,+1);
                    sol[i] = pj.placed()?Placement{pj.day,pj.ts_idx,pj.room_idx,wti}:Placement{};
                    sol[j] = pi.placed()?Placement{pi.day,pi.ts_idx,pi.room_idx,wtj}:Placement{};
                    cur_score += delta; accepted = true;
                } else {
                    if (pi.placed()) bm.apply(pb,ti,pi.day,pi.ts_idx,pi.room_idx,pi.wt,+1);
                    if (pj.placed()) bm.apply(pb,tj,pj.day,pj.ts_idx,pj.room_idx,pj.wt,+1);
                }
            }

        } else if (mv == 2) {
            int i = rTask(rng);
            const Task& task = pb.tasks[i];
            if (!task.is_wt_flexible) goto upd;
            Placement& p = sol[i];
            if (!p.placed()) goto upd;
            {
                WeekType nwt = (p.wt==WeekType::RED)?WeekType::BLUE:WeekType::RED;
                bm.apply(pb,task,p.day,p.ts_idx,p.room_idx,p.wt,-1);
                if (!bm.hasConflict(pb,task,p.day,p.ts_idx,p.room_idx,nwt)) {
                    double os = slotScore(bm,pb,task,p.day,p.ts_idx,p.room_idx,p.wt);
                    double ns2= slotScore(bm,pb,task,p.day,p.ts_idx,p.room_idx,nwt);
                    delta = ns2 - os;
                    if (delta>0.0 || rU(rng)<exp(delta/T)) {
                        bm.apply(pb,task,p.day,p.ts_idx,p.room_idx,nwt,+1);
                        p.wt = nwt; cur_score += delta; accepted = true;
                    } else bm.apply(pb,task,p.day,p.ts_idx,p.room_idx,p.wt,+1);
                } else bm.apply(pb,task,p.day,p.ts_idx,p.room_idx,p.wt,+1);
            }

        } else if (mv == 3) {
            int i = rTask(rng);
            const Task& task = pb.tasks[i];
            Placement& p = sol[i];
            if (!p.placed()) goto upd;
            {
                int nr = rRoom(rng);
                if (nr == p.room_idx) goto upd;
                if (!roomIsCompatible(pb,task,pb.rooms[nr])) goto upd;
                if (!capacityOk(pb,task,pb.rooms[nr])) goto upd;
                bm.apply(pb,task,p.day,p.ts_idx,p.room_idx,p.wt,-1);
                if (!bm.hasConflict(pb,task,p.day,p.ts_idx,nr,p.wt)) {
                    double os = slotScore(bm,pb,task,p.day,p.ts_idx,p.room_idx,p.wt);
                    double ns2= slotScore(bm,pb,task,p.day,p.ts_idx,nr,p.wt);
                    delta = ns2 - os;
                    if (delta>0.0 || rU(rng)<exp(delta/T)) {
                        bm.apply(pb,task,p.day,p.ts_idx,nr,p.wt,+1);
                        p.room_idx = (int16_t)nr; cur_score += delta; accepted = true;
                    } else bm.apply(pb,task,p.day,p.ts_idx,p.room_idx,p.wt,+1);
                } else bm.apply(pb,task,p.day,p.ts_idx,p.room_idx,p.wt,+1);
            }

        } else if (mv == 4) {
            int i = rTask(rng);
            const Task& task = pb.tasks[i];
            Placement& p = sol[i];
            if (!p.placed()) goto upd;
            {
                int nd = rDay(rng);
                if (nd == p.day) goto upd;
                bm.apply(pb,task,p.day,p.ts_idx,p.room_idx,p.wt,-1);
                if (!bm.hasConflict(pb,task,nd,p.ts_idx,p.room_idx,p.wt)) {
                    double os = slotScore(bm,pb,task,p.day,p.ts_idx,p.room_idx,p.wt);
                    double ns2= slotScore(bm,pb,task,nd,p.ts_idx,p.room_idx,p.wt);
                    delta = ns2 - os;
                    if (delta>0.0 || rU(rng)<exp(delta/T)) {
                        bm.apply(pb,task,nd,p.ts_idx,p.room_idx,p.wt,+1);
                        p.day = (int8_t)nd; cur_score += delta; accepted = true;
                    } else bm.apply(pb,task,p.day,p.ts_idx,p.room_idx,p.wt,+1);
                } else bm.apply(pb,task,p.day,p.ts_idx,p.room_idx,p.wt,+1);
            }

        } else if (mv == 5) {
            int i = rTask(rng);
            const Task& task = pb.tasks[i];
            Placement& p = sol[i];
            if (!p.placed()) goto upd;
            {
                int ns_idx = p.ts_idx + (rU(rng)<0.5 ? -1 : +1);
                if (ns_idx < 0 || ns_idx >= nS) goto upd;
                bm.apply(pb,task,p.day,p.ts_idx,p.room_idx,p.wt,-1);
                if (!bm.hasConflict(pb,task,p.day,ns_idx,p.room_idx,p.wt)) {
                    double os = slotScore(bm,pb,task,p.day,p.ts_idx,p.room_idx,p.wt);
                    double ns2= slotScore(bm,pb,task,p.day,ns_idx,p.room_idx,p.wt);
                    delta = ns2 - os;
                    if (delta>0.0 || rU(rng)<exp(delta/T)) {
                        bm.apply(pb,task,p.day,ns_idx,p.room_idx,p.wt,+1);
                        p.ts_idx = (int8_t)ns_idx; cur_score += delta; accepted = true;
                    } else bm.apply(pb,task,p.day,p.ts_idx,p.room_idx,p.wt,+1);
                } else bm.apply(pb,task,p.day,p.ts_idx,p.room_idx,p.wt,+1);
            }

        } else if (mv == 6) {
            int i = rTask(rng);
            const Task& task = pb.tasks[i];
            Placement& p = sol[i];
            if (!p.placed()) goto upd;
            {
                int nd = rDay(rng), nts = rSlot(rng);
                WeekType nwt = task.is_wt_flexible
                    ? (rU(rng)<0.5?WeekType::RED:WeekType::BLUE) : task.week_pref;
                bm.apply(pb,task,p.day,p.ts_idx,p.room_idx,p.wt,-1);
                if (!bm.hasConflict(pb,task,nd,nts,p.room_idx,nwt)) {
                    double os = slotScore(bm,pb,task,p.day,p.ts_idx,p.room_idx,p.wt);
                    double ns2= slotScore(bm,pb,task,nd,nts,p.room_idx,nwt);
                    delta = ns2 - os;
                    if (delta>0.0 || rU(rng)<exp(delta/T)) {
                        bm.apply(pb,task,nd,nts,p.room_idx,nwt,+1);
                        p.day=(int8_t)nd; p.ts_idx=(int8_t)nts; p.wt=nwt;
                        cur_score += delta; accepted = true;
                    } else bm.apply(pb,task,p.day,p.ts_idx,p.room_idx,p.wt,+1);
                } else bm.apply(pb,task,p.day,p.ts_idx,p.room_idx,p.wt,+1);
            }

        } else {
            int i = rTask(rng);
            const Task& task = pb.tasks[i];
            Placement& p = sol[i];
            double os = p.placed()
                ? slotScore(bm,pb,task,p.day,p.ts_idx,p.room_idx,p.wt)
                : SC::UNPLACED;
            if (p.placed()) bm.apply(pb,task,p.day,p.ts_idx,p.room_idx,p.wt,-1);

            vector<WeekType> wt_opts = task.is_wt_flexible
                ? vector<WeekType>{WeekType::RED,WeekType::BLUE}
                : vector<WeekType>{task.week_pref};

            double best_new = SC::UNPLACED;
            Placement best_p;
            int attempts = min(nD * nS * nR, 200);
            for (int att = 0; att < attempts; att++) {
                int d = rDay(rng), s = rSlot(rng), r = rRoom(rng);
                WeekType wt = wt_opts[rng() % wt_opts.size()];
                if (!roomIsCompatible(pb,task,pb.rooms[r])) continue;
                if (!capacityOk(pb,task,pb.rooms[r])) continue;
                if (bm.hasConflict(pb,task,d,s,r,wt)) continue;
                double sc = slotScore(bm,pb,task,d,s,r,wt);
                if (sc > best_new) { best_new = sc; best_p = {(int8_t)d,(int8_t)s,(int16_t)r,wt}; }
            }

            delta = best_new - os;
            if (delta > 0.0 || rU(rng) < exp(delta/T)) {
                if (best_new > SC::UNPLACED) {
                    bm.apply(pb,task,best_p.day,best_p.ts_idx,best_p.room_idx,best_p.wt,+1);
                    p = best_p;
                } else {
                    p = {};
                }
                cur_score += delta; accepted = true;
            } else {
                if (p.placed()) bm.apply(pb,task,p.day,p.ts_idx,p.room_idx,p.wt,+1);
            }
        }

        if (accepted && cur_score > best_score) {
            best_score = cur_score;
            best_sol   = sol;
        }

        upd:
        mst[mv].trials++;
        if (accepted) mst[mv].reward += max(0.0, delta);
        total_trials++;

        T *= cooling;
        if (T < 0.005) T = 0.005;
    }

    return best_sol;
}

static vector<Placement> populationCrossover(
    const Problem& pb,
    const vector<pair<double,vector<Placement>>>& pop,
    mt19937& rng)
{
    if (pop.size() < 2) return pop[0].second;
    int nT = pb.nTasks();
    const auto& p1 = pop[0].second;
    const auto& p2 = pop[1].second;

    uniform_int_distribution<int> rCut(1, nT-1);
    int cut = rCut(rng);

    vector<Placement> child;
    child.reserve(nT);
    for (int i = 0; i < cut; i++) child.push_back(p1[i]);
    for (int i = cut; i < nT; i++) child.push_back(p2[i]);

    BusyMap bm;
    bm.init(pb.nTeachers(), pb.nGroups(), pb.nRooms(), pb.nDays(), pb.nSlots());
    for (int i = 0; i < nT; i++) {
        const Task& task = pb.tasks[i];
        Placement& p = child[i];
        if (p.placed() && !bm.hasConflict(pb,task,p.day,p.ts_idx,p.room_idx,p.wt)) {
            bm.apply(pb,task,p.day,p.ts_idx,p.room_idx,p.wt,+1);
        } else if (p.placed()) {
            p = {};
        }
    }
    return child;
}
struct Result {
    vector<Placement> sol;
    double            score;
    int               placed, unplaced;
    double            elapsed_ms;
};

static Result solveProblem(const Problem& pb) {
    if (pb.nTasks() == 0 || pb.nRooms() == 0 || pb.nSlots() == 0)
        return {{}, 0.0, 0, 0, 0.0};

    auto t0       = Clock::now();
    auto deadline = t0 + chrono::seconds(pb.max_seconds);

    int n_threads = min(pb.sa_restarts,
                        max(1, (int)thread::hardware_concurrency()));
    cerr << "[engine] threads=" << n_threads
         << "  restarts=" << pb.sa_restarts
         << "  steps/restart=" << pb.sa_steps << "\n";

    mutex pop_mutex;
    constexpr int POP_SIZE = 5;
    vector<pair<double,vector<Placement>>> population; // (score, sol)

    int total_restarts = pb.sa_restarts;
    int batch_size = (total_restarts + n_threads - 1) / n_threads;

    auto worker = [&](int thread_id, int start_restart, int end_restart) {
        for (int restart = start_restart; restart < end_restart; restart++) {
            if (Clock::now() > deadline) break;

            mt19937 rng(42 + restart * 1337 + thread_id * 97);

            BusyMap bm;
            bm.init(pb.nTeachers(), pb.nGroups(), pb.nRooms(),
                    pb.nDays(), pb.nSlots());

            vector<Placement> sol = greedySeed(pb, bm, rng);

            double T = pb.sa_t0 * pow(pb.sa_reheat,
                                      (double)restart / max(1, total_restarts - 1));

            sol = anneal(pb, sol, bm, rng, T,
                         pb.sa_cooling, pb.sa_steps, deadline);

            double sc = fullScore(pb, sol);
            int placed = (int)count_if(sol.begin(), sol.end(),
                [](const Placement& p){ return p.placed(); });

            cerr << "[restart " << (restart+1) << "/" << total_restarts
                 << "  score=" << fixed << setprecision(1) << sc
                 << "  placed=" << placed << "/" << pb.nTasks() << "]\n";

            {
                lock_guard<mutex> lock(pop_mutex);
                population.emplace_back(sc, sol);
                sort(population.begin(), population.end(),
                     [](const auto& a, const auto& b){ return a.first > b.first; });
                if ((int)population.size() > POP_SIZE)
                    population.resize(POP_SIZE);
            }
        }
    };

    vector<thread> threads;
    int r = 0;
    for (int t = 0; t < n_threads && r < total_restarts; t++) {
        int start = r;
        int end   = min(r + batch_size, total_restarts);
        threads.emplace_back(worker, t, start, end);
        r = end;
    }
    for (auto& th : threads) th.join();

    if ((int)population.size() >= 2) {
        mt19937 rng_cx(999);
        cerr << "[engine] population crossover (pool=" << population.size() << ")\n";
        for (int cx = 0; cx < 5 && (int)population.size() >= 2; cx++) {
            auto child = populationCrossover(pb, population, rng_cx);
            double sc  = fullScore(pb, child);
            population.emplace_back(sc, child);
        }
        sort(population.begin(), population.end(),
             [](const auto& a, const auto& b){ return a.first > b.first; });
        if ((int)population.size() > POP_SIZE)
            population.resize(POP_SIZE);
    }

    auto deadline2 = Clock::now() + chrono::seconds(5);
    if (!population.empty() && Clock::now() < deadline2) {
        mt19937 rng_f(77777);
        BusyMap bm_f;
        bm_f.init(pb.nTeachers(), pb.nGroups(), pb.nRooms(), pb.nDays(), pb.nSlots());
        const auto& best_ref = population[0].second;
        for (int i = 0; i < pb.nTasks(); i++) {
            if (best_ref[i].placed())
                bm_f.apply(pb, pb.tasks[i],
                           best_ref[i].day, best_ref[i].ts_idx,
                           best_ref[i].room_idx, best_ref[i].wt, +1);
        }
        auto fsol = anneal(pb, population[0].second, bm_f, rng_f,
                           50.0, 0.9999, 50000, deadline2);
        double fsc = fullScore(pb, fsol);
        cerr << "[engine] final polish: score=" << fsc << "\n";
        if (fsc > population[0].first)
            population[0] = {fsc, fsol};
    }

    if (population.empty())
        return {{}, SC::UNPLACED * pb.nTasks(), 0, pb.nTasks(), 0.0};

    const auto& [best_sc, best_sol] = population[0];
    int placed   = (int)count_if(best_sol.begin(), best_sol.end(),
                                 [](const Placement& p){ return p.placed(); });
    int unplaced = pb.nTasks() - placed;
    double elapsed = chrono::duration<double,milli>(Clock::now() - t0).count();

    cerr << "[engine] DONE  score=" << fixed << setprecision(1) << best_sc
         << "  placed=" << placed << "/" << pb.nTasks()
         << "  time=" << (int)elapsed << "ms\n";

    return {best_sol, best_sc, placed, unplaced, elapsed};
}
static json buildOutput(const Problem& pb, const Result& res) {
    json out;
    out["success"]        = true;
    out["score"]          = res.score;
    out["placed_count"]   = res.placed;
    out["unplaced_count"] = res.unplaced;
    out["total_tasks"]    = pb.nTasks();
    out["elapsed_ms"]     = res.elapsed_ms;

    json slots_arr = json::array();
    vector<string> unassigned;

    const bool has_sol = !res.sol.empty();

    for (int i = 0; i < pb.nTasks(); i++) {
        const Task& task = pb.tasks[i];
        const Placement& p = has_sol ? res.sol[i] : Placement{};

        if (!p.placed()) {
            unassigned.push_back(
                task.subject_name + " (" + ltToStr(task.ltype)
                + " / " + wtToStr(task.week_pref) + ")");
            continue;
        }

        const Room&  room = pb.rooms[p.room_idx];
        const TSlot& ts   = pb.slots[p.ts_idx];

        for (int k = 0; k < (int)task.group_ids.size(); k++) {
            json slot;
            slot["group_id"]     = task.group_ids[k];
            slot["subject_id"]   = task.subject_id;
            slot["subject_name"] = task.subject_name;
            slot["teacher_id"]   = task.teacher_id;
            slot["day_of_week"]  = (int)p.day;
            slot["time_slot_id"] = ts.id;
            slot["start_time"]   = ts.start;
            slot["end_time"]     = ts.end;
            slot["classroom_id"] = room.id;
            slot["room_number"]  = room.number;
            slot["lesson_type"]  = ltToStr(task.ltype);
            slot["week_type"]    = wtToStr(p.wt);
            slot["is_stream"]    = task.is_stream;
            slot["stream_tag"]   = task.stream_tag;
            slot["is_active"]    = true;
            slots_arr.push_back(slot);
        }
    }

    out["schedule"] = slots_arr;
    {
        json ua = json::array();
        for (const auto& s : unassigned) ua.push_back(json(s));
        out["unassigned_details"] = ua;
    }
    return out;
}

int main(int argc, char* argv[]) {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    string input;
    if (argc >= 2) {
        ifstream f(argv[1]);
        if (!f) { cerr << "Cannot open: " << argv[1] << "\n"; return 1; }
        input.assign(istreambuf_iterator<char>(f), {});
    } else {
        input.assign(istreambuf_iterator<char>(cin), {});
    }
    if (input.empty()) {
        json e; e["success"]=false; e["error"]="Empty input";
        cout << e.dump(2) << "\n"; return 1;
    }

    json j;
    try { j = json::parse(input); }
    catch (const exception& e) {
        json err; err["success"]=false; err["error"]=e.what();
        cout << err.dump(2) << "\n"; return 1;
    }

    Problem pb;
    try { pb = parseInput(j); }
    catch (const exception& e) {
        json err; err["success"]=false; err["error"]=string("parse: ")+e.what();
        cout << err.dump(2) << "\n"; return 1;
    }

    cerr << "[engine] tasks="     << pb.nTasks()
         << "  rooms="            << pb.nRooms()
         << "  slots="            << pb.nSlots()
         << "  teachers="         << pb.nTeachers()
         << "  groups="           << pb.nGroups()
         << "  overflow_mode="    << pb.overflow_mode
         << "  strict="           << pb.strict_room_types
         << "  avoid_gaps="       << pb.avoid_gaps << "\n";

    int cnt_ev=0, cnt_rd=0, cnt_bl=0, cnt_fl=0;
    for (const auto& t : pb.tasks) {
        if (t.week_pref==WeekType::EVERY) cnt_ev++;
        else if (t.week_pref==WeekType::RED) cnt_rd++;
        else cnt_bl++;
        if (t.is_wt_flexible) cnt_fl++;
    }
    cerr << "[engine] week_types EVERY=" << cnt_ev
         << " RED=" << cnt_rd
         << " BLUE=" << cnt_bl
         << " flexible=" << cnt_fl << "\n";

    Result res = solveProblem(pb);
    json out   = buildOutput(pb, res);

    if (argc >= 3) {
        ofstream f(argv[2]);
        if (!f) { cerr << "Cannot write: " << argv[2] << "\n"; return 1; }
        f << out.dump(2) << "\n";
        cerr << "[engine] output -> " << argv[2] << "\n";
    } else {
        cout << out.dump(2) << "\n";
    }
    return 0;
}