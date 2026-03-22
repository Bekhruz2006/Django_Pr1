#pragma once
#include <string>
#include <vector>
#include <map>
#include <stdexcept>
#include <sstream>
#include <cmath>
#include <cstdint>

namespace nlohmann {

class json {
public:
    enum class value_t { null_t, bool_t, int_t, float_t, string_t, array_t, object_t };

    using array_type  = std::vector<json>;
    using object_type = std::map<std::string, json>;

    using iterator       = array_type::iterator;
    using const_iterator = array_type::const_iterator;

    struct obj_iterator {
        object_type::const_iterator it;
        const json& second() const { return it->second; }
        bool operator==(const obj_iterator& o) const { return it == o.it; }
        bool operator!=(const obj_iterator& o) const { return it != o.it; }
    };

private:
    value_t type_ = value_t::null_t;
    bool        b_ = false;
    int64_t     i_ = 0;
    double      d_ = 0.0;
    std::string s_;
    array_type  arr_;
    object_type obj_;

public:
    json() : type_(value_t::null_t) {}
    json(bool v)              : type_(value_t::bool_t),   b_(v) {}
    json(int v)               : type_(value_t::int_t),    i_(v) {}
    json(unsigned v)          : type_(value_t::int_t),    i_(v) {}
    json(int64_t v)           : type_(value_t::int_t),    i_(v) {}
    json(double v)            : type_(value_t::float_t),  d_(v) {}
    json(float v)             : type_(value_t::float_t),  d_(v) {}
    json(const std::string& v): type_(value_t::string_t), s_(v) {}
    json(const char* v)       : type_(value_t::string_t), s_(v ? v : "") {}
    json(std::nullptr_t)      : type_(value_t::null_t) {}

    static json array()  { json j; j.type_ = value_t::array_t;  return j; }
    static json object() { json j; j.type_ = value_t::object_t; return j; }

    bool is_null()   const { return type_ == value_t::null_t; }
    bool is_bool()   const { return type_ == value_t::bool_t; }
    bool is_number() const { return type_ == value_t::int_t || type_ == value_t::float_t; }
    bool is_string() const { return type_ == value_t::string_t; }
    bool is_array()  const { return type_ == value_t::array_t; }
    bool is_object() const { return type_ == value_t::object_t; }

    iterator       begin()       { return arr_.begin(); }
    iterator       end()         { return arr_.end(); }
    const_iterator begin() const { return arr_.cbegin(); }
    const_iterator end()   const { return arr_.cend(); }

    size_t size() const {
        if (type_ == value_t::array_t)  return arr_.size();
        if (type_ == value_t::object_t) return obj_.size();
        return 0;
    }
    bool empty() const { return size() == 0; }

    json& operator[](size_t idx)             { return arr_[idx]; }
    const json& operator[](size_t idx) const { return arr_[idx]; }
    void push_back(const json& v) {
        if (type_ == value_t::null_t) type_ = value_t::array_t;
        arr_.push_back(v);
    }

    json& operator[](const std::string& key) {
        if (type_ == value_t::null_t) type_ = value_t::object_t;
        return obj_[key];
    }
    json& operator[](const char* key) {
        if (type_ == value_t::null_t) type_ = value_t::object_t;
        return obj_[key];
    }
    const json& operator[](const std::string& key) const {
        auto it = obj_.find(key);
        if (it == obj_.end()) throw std::runtime_error("key not found: " + key);
        return it->second;
    }

    const json& at(const std::string& key) const {
        auto it = obj_.find(key);
        if (it == obj_.end()) throw std::runtime_error("key not found: " + key);
        return it->second;
    }
    json& at(const std::string& key) {
        auto it = obj_.find(key);
        if (it == obj_.end()) throw std::runtime_error("key not found: " + key);
        return it->second;
    }

    obj_iterator obj_find(const std::string& key) const {
        return {obj_.find(key)};
    }
    obj_iterator obj_end() const {
        return {obj_.end()};
    }

    const json* find_ptr(const std::string& key) const {
        auto it = obj_.find(key);
        if (it == obj_.end()) return nullptr;
        return &it->second;
    }

    template<typename T> T get() const;

    static json parse(const std::string& s) {
        size_t i = 0;
        return parse_value(s, i);
    }

private:
    static void skip_ws(const std::string& s, size_t& i) {
        while (i < s.size() && (s[i]==' '||s[i]=='\t'||s[i]=='\n'||s[i]=='\r')) i++;
    }
    static json parse_value(const std::string& s, size_t& i) {
        skip_ws(s, i);
        if (i >= s.size()) throw std::runtime_error("unexpected end of input");
        char c = s[i];
        if (c == '{') return parse_object(s, i);
        if (c == '[') return parse_array(s, i);
        if (c == '"') return json(parse_string(s, i));
        if (c == 't') { if(i+3<s.size()) i+=4; return json(true); }
        if (c == 'f') { if(i+4<s.size()) i+=5; return json(false); }
        if (c == 'n') { if(i+3<s.size()) i+=4; return json(nullptr); }
        return parse_number(s, i);
    }
    static json parse_object(const std::string& s, size_t& i) {
        json obj; obj.type_ = value_t::object_t;
        i++;
        skip_ws(s, i);
        if (i < s.size() && s[i] == '}') { i++; return obj; }
        while (i < s.size()) {
            skip_ws(s, i);
            std::string key = parse_string(s, i);
            skip_ws(s, i);
            if (i >= s.size() || s[i] != ':') throw std::runtime_error("expected ':'");
            i++;
            json val = parse_value(s, i);
            obj.obj_[key] = std::move(val);
            skip_ws(s, i);
            if (i < s.size() && s[i] == '}') { i++; return obj; }
            if (i < s.size() && s[i] == ',') { i++; continue; }
            throw std::runtime_error("expected ',' or '}'");
        }
        throw std::runtime_error("unterminated object");
    }
    static json parse_array(const std::string& s, size_t& i) {
        json arr; arr.type_ = value_t::array_t;
        i++;
        skip_ws(s, i);
        if (i < s.size() && s[i] == ']') { i++; return arr; }
        while (i < s.size()) {
            arr.arr_.push_back(parse_value(s, i));
            skip_ws(s, i);
            if (i < s.size() && s[i] == ']') { i++; return arr; }
            if (i < s.size() && s[i] == ',') { i++; continue; }
            throw std::runtime_error("expected ',' or ']'");
        }
        throw std::runtime_error("unterminated array");
    }
    static std::string parse_string(const std::string& s, size_t& i) {
        if (i >= s.size() || s[i] != '"')
            throw std::runtime_error("expected '\"'");
        i++;
        std::string result;
        while (i < s.size() && s[i] != '"') {
            if (s[i] == '\\') {
                i++;
                if (i >= s.size()) break;
                char e = s[i++];
                switch(e) {
                    case 'n': result+='\n'; break;
                    case 't': result+='\t'; break;
                    case 'r': result+='\r'; break;
                    case '"': result+='"';  break;
                    case '\\': result+='\\'; break;
                    case '/': result+='/';  break;
                    default:  result+=e;   break;
                }
            } else {
                result += s[i++];
            }
        }
        if (i < s.size()) i++; 
        return result;
    }
    static json parse_number(const std::string& s, size_t& i) {
        size_t start = i;
        bool is_float = false;
        if (i < s.size() && s[i] == '-') i++;
        while (i < s.size() && s[i] >= '0' && s[i] <= '9') i++;
        if (i < s.size() && s[i] == '.') {
            is_float = true; i++;
            while (i < s.size() && s[i] >= '0' && s[i] <= '9') i++;
        }
        if (i < s.size() && (s[i]=='e'||s[i]=='E')) {
            is_float = true; i++;
            if (i < s.size() && (s[i]=='+'||s[i]=='-')) i++;
            while (i < s.size() && s[i] >= '0' && s[i] <= '9') i++;
        }
        std::string num = s.substr(start, i - start);
        if (num.empty()) throw std::runtime_error("invalid number");
        if (is_float) return json(std::stod(num));
        return json((int64_t)std::stoll(num));
    }

    static void escape_string(std::ostream& os, const std::string& s) {
        os << '"';
        for (unsigned char c : s) {
            if (c == '"')  os << "\\\"";
            else if (c == '\\') os << "\\\\";
            else if (c == '\n') os << "\\n";
            else if (c == '\r') os << "\\r";
            else if (c == '\t') os << "\\t";
            else os << (char)c;
        }
        os << '"';
    }

    void dump_impl(std::ostream& os, int indent, int depth) const {
        std::string nl   = (indent > 0) ? "\n" : "";
        std::string pad  (depth * indent, ' ');
        std::string inner((depth + 1) * indent, ' ');

        switch (type_) {
        case value_t::null_t:   os << "null"; break;
        case value_t::bool_t:   os << (b_ ? "true" : "false"); break;
        case value_t::int_t:    os << i_; break;
        case value_t::float_t:
            if (std::isfinite(d_)) {
                std::ostringstream tmp;
                tmp << std::setprecision(10) << d_;
                os << tmp.str();
            } else { os << "null"; }
            break;
        case value_t::string_t: escape_string(os, s_); break;
        case value_t::array_t:
            if (arr_.empty()) { os << "[]"; break; }
            os << "[";
            for (size_t k = 0; k < arr_.size(); k++) {
                if (indent > 0) os << nl << inner;
                arr_[k].dump_impl(os, indent, depth + 1);
                if (k + 1 < arr_.size()) os << ",";
            }
            if (indent > 0) os << nl << pad;
            os << "]";
            break;
        case value_t::object_t:
            if (obj_.empty()) { os << "{}"; break; }
            os << "{";
            {
                size_t k = 0;
                for (const auto& [key, val] : obj_) {
                    if (indent > 0) os << nl << inner;
                    escape_string(os, key);
                    os << (indent > 0 ? ": " : ":");
                    val.dump_impl(os, indent, depth + 1);
                    if (++k < obj_.size()) os << ",";
                }
            }
            if (indent > 0) os << nl << pad;
            os << "}";
            break;
        }
    }

public:
    std::string dump(int indent = -1) const {
        std::ostringstream os;
        dump_impl(os, indent < 0 ? 0 : indent, 0);
        return os.str();
    }
};

template<> inline bool json::get<bool>() const {
    if (type_==value_t::bool_t)  return b_;
    if (type_==value_t::int_t)   return i_ != 0;
    return false;
}
template<> inline int json::get<int>() const {
    if (type_==value_t::int_t)   return (int)i_;
    if (type_==value_t::float_t) return (int)d_;
    return 0;
}
template<> inline int64_t json::get<int64_t>() const {
    if (type_==value_t::int_t)   return i_;
    if (type_==value_t::float_t) return (int64_t)d_;
    return 0;
}
template<> inline double json::get<double>() const {
    if (type_==value_t::float_t) return d_;
    if (type_==value_t::int_t)   return (double)i_;
    return 0.0;
}
template<> inline float json::get<float>() const { return (float)get<double>(); }
template<> inline std::string json::get<std::string>() const {
    if (type_==value_t::string_t) return s_;
    return "";
}

} 

#include <iomanip>