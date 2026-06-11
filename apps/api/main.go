package main

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	_ "modernc.org/sqlite"
)

type Server struct {
	root   string
	dbPath string
	db     *sql.DB
}

func main() {
	root, err := findRoot()
	if err != nil {
		log.Fatal(err)
	}
	dbPath := filepath.Join(root, "data", "health.sqlite")
	if env := os.Getenv("RECOVERYIQ_DB"); env != "" {
		dbPath = env
	}
	if err := os.MkdirAll(filepath.Dir(dbPath), 0o755); err != nil {
		log.Fatal(err)
	}

	db, err := sql.Open("sqlite", dbPath)
	if err != nil {
		log.Fatal(err)
	}
	defer db.Close()

	s := &Server{root: root, dbPath: dbPath, db: db}
	mux := http.NewServeMux()
	mux.HandleFunc("/api/health", s.health)
	mux.HandleFunc("/api/sync", s.sync)
	mux.HandleFunc("/api/today", s.today)
	mux.HandleFunc("/api/sleep", s.sleepList)
	mux.HandleFunc("/api/recovery", s.recoveryList)
	mux.HandleFunc("/api/energy", s.list("energy_windows", "date DESC"))
	mux.HandleFunc("/api/naps", s.list("daily_naps", "date DESC"))

	addr := getenv("PORT", "8080")
	log.Printf("Recovery IQ API listening on http://localhost:%s", addr)
	log.Printf("SQLite: %s", dbPath)
	log.Fatal(http.ListenAndServe(":"+addr, withCORS(mux)))
}

func findRoot() (string, error) {
	if env := os.Getenv("RECOVERYIQ_ROOT"); env != "" {
		return filepath.Abs(env)
	}
	cwd, _ := os.Getwd()
	candidates := []string{
		cwd,
		filepath.Join(cwd, ".."),
		filepath.Join(cwd, "..", ".."),
	}
	for _, c := range candidates {
		abs, _ := filepath.Abs(c)
		if _, err := os.Stat(filepath.Join(abs, "services", "garmin-sync", "sync.py")); err == nil {
			return abs, nil
		}
	}
	return "", errors.New("could not find project root; set RECOVERYIQ_ROOT")
}

func getenv(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func withCORS(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type")
		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusNoContent)
			return
		}
		next.ServeHTTP(w, r)
	})
}

func (s *Server) health(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		methodNotAllowed(w)
		return
	}
	counts := map[string]int{"daily_sleep": 0, "daily_naps": 0, "daily_recovery": 0, "energy_windows": 0}
	for table := range counts {
		var count int
		if err := s.db.QueryRow("SELECT COUNT(*) FROM " + table).Scan(&count); err == nil {
			counts[table] = count
		}
	}
	writeJSON(w, map[string]any{
		"ok":       true,
		"database": s.dbPath,
		"counts":   counts,
		"message":  "Recovery IQ estimates are informational only, not medical advice.",
	})
}

func (s *Server) sync(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		methodNotAllowed(w)
		return
	}
	days := intParam(r, "days", 14)
	if days < 1 {
		days = 1
	}
	if days > 90 {
		days = 90
	}

	ctx, cancel := context.WithTimeout(r.Context(), 3*time.Minute)
	defer cancel()

	python := filepath.Join(s.root, "services", "garmin-sync", ".venv", "bin", "python")
	if _, err := os.Stat(python); err != nil {
		python = "python3"
	}
	script := filepath.Join(s.root, "services", "garmin-sync", "sync.py")
	cmd := exec.CommandContext(ctx, python, script, "--days", strconv.Itoa(days))
	cmd.Dir = s.root
	cmd.Env = append(os.Environ(), "RECOVERYIQ_DB="+s.dbPath)
	out, err := cmd.CombinedOutput()
	if err != nil {
		writeError(w, http.StatusInternalServerError, fmt.Sprintf("sync failed: %v", err), string(out))
		return
	}
	writeJSON(w, map[string]any{"ok": true, "output": string(out)})
}

func (s *Server) today(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		methodNotAllowed(w)
		return
	}
	var latest string
	if err := s.db.QueryRow("SELECT date FROM daily_sleep ORDER BY date DESC LIMIT 1").Scan(&latest); err != nil {
		writeError(w, http.StatusNotFound, "no data found; run make sync or POST /api/sync?days=30", "")
		return
	}
	sleep, _ := one(s.db, "SELECT * FROM daily_sleep WHERE date = ?", latest)
	naps, _ := many(s.db, "SELECT * FROM daily_naps WHERE date = ? ORDER BY nap_start ASC", latest)
	recovery, _ := one(s.db, "SELECT * FROM daily_recovery WHERE date = ?", latest)
	energy, _ := one(s.db, "SELECT * FROM energy_windows WHERE date = ?", latest)
	writeJSON(w, map[string]any{
		"date":       latest,
		"sleep":      sleep,
		"naps":       naps,
		"recovery":   recovery,
		"energy":     energy,
		"disclaimer": "All energy windows and melatonin timing are estimates, not medical claims.",
	})
}

func (s *Server) sleepList(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		methodNotAllowed(w)
		return
	}
	days := intParam(r, "days", 30)
	if days < 1 {
		days = 1
	}
	if days > 365 {
		days = 365
	}
	rows, err := many(s.db, `
		SELECT * FROM (
			SELECT ds.*,
				ew.acute_sleep_debt_minutes,
				ew.chronic_sleep_deficit_minutes_per_night,
				ew.chronic_deficit_label,
				ew.decayed_sleep_debt_minutes,
				ew.sleep_consistency_score,
				ew.recovery_score,
				ew.recovery_label,
				ew.sleep_pressure_label,
				ew.model_version,
				ew.calculation_explanation,
				ew.base_sleep_need_minutes,
				ew.next_day_sleep_need_minutes,
				ew.sleep_need_adjustment_minutes,
				ew.acute_debt_repay_minutes,
				ew.chronic_deficit_repay_minutes,
				ew.nap_credit_minutes,
				ew.recovery_penalty_minutes,
				ew.dynamic_wake_span_minutes
			FROM daily_sleep ds
			LEFT JOIN energy_windows ew ON ew.date = ds.date
			ORDER BY ds.date DESC
			LIMIT ?
		) ORDER BY date ASC`, days)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error(), "")
		return
	}
	writeJSON(w, rows)
}

func (s *Server) recoveryList(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		methodNotAllowed(w)
		return
	}
	days := intParam(r, "days", 30)
	if days < 1 {
		days = 1
	}
	if days > 365 {
		days = 365
	}
	rows, err := many(s.db, `
		SELECT * FROM (
			SELECT dr.*,
				ew.acute_sleep_debt_minutes,
				ew.chronic_sleep_deficit_minutes_per_night,
				ew.chronic_deficit_label,
				ew.decayed_sleep_debt_minutes,
				ew.sleep_consistency_score,
				ew.recovery_score,
				ew.recovery_label,
				ew.sleep_pressure_label,
				ew.model_version,
				ew.calculation_explanation,
				ew.base_sleep_need_minutes,
				ew.next_day_sleep_need_minutes,
				ew.sleep_need_adjustment_minutes,
				ew.acute_debt_repay_minutes,
				ew.chronic_deficit_repay_minutes,
				ew.nap_credit_minutes,
				ew.recovery_penalty_minutes,
				ew.dynamic_wake_span_minutes
			FROM daily_recovery dr
			LEFT JOIN energy_windows ew ON ew.date = dr.date
			ORDER BY dr.date DESC
			LIMIT ?
		) ORDER BY date ASC`, days)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error(), "")
		return
	}
	writeJSON(w, rows)
}

func (s *Server) list(table, order string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			methodNotAllowed(w)
			return
		}
		days := intParam(r, "days", 30)
		if days < 1 {
			days = 1
		}
		if days > 365 {
			days = 365
		}
		query := fmt.Sprintf("SELECT * FROM (SELECT * FROM %s ORDER BY %s LIMIT ?) ORDER BY date ASC", table, order)
		rows, err := many(s.db, query, days)
		if err != nil {
			writeError(w, http.StatusInternalServerError, err.Error(), "")
			return
		}
		writeJSON(w, rows)
	}
}

func intParam(r *http.Request, name string, fallback int) int {
	v := strings.TrimSpace(r.URL.Query().Get(name))
	if v == "" {
		return fallback
	}
	n, err := strconv.Atoi(v)
	if err != nil {
		return fallback
	}
	return n
}

func one(db *sql.DB, query string, args ...any) (map[string]any, error) {
	rows, err := many(db, query, args...)
	if err != nil {
		return nil, err
	}
	if len(rows) == 0 {
		return map[string]any{}, nil
	}
	return rows[0], nil
}

func many(db *sql.DB, query string, args ...any) ([]map[string]any, error) {
	rows, err := db.Query(query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	cols, err := rows.Columns()
	if err != nil {
		return nil, err
	}
	result := make([]map[string]any, 0)
	for rows.Next() {
		values := make([]any, len(cols))
		ptrs := make([]any, len(cols))
		for i := range values {
			ptrs[i] = &values[i]
		}
		if err := rows.Scan(ptrs...); err != nil {
			return nil, err
		}
		row := make(map[string]any, len(cols))
		for i, col := range cols {
			switch v := values[i].(type) {
			case []byte:
				row[col] = string(v)
			default:
				row[col] = v
			}
		}
		result = append(result, row)
	}
	return result, rows.Err()
}

func writeJSON(w http.ResponseWriter, v any) {
	w.Header().Set("Content-Type", "application/json")
	if err := json.NewEncoder(w).Encode(v); err != nil {
		log.Printf("json encode failed: %v", err)
	}
}

func writeError(w http.ResponseWriter, status int, message, details string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(map[string]any{"ok": false, "error": message, "details": details})
}

func methodNotAllowed(w http.ResponseWriter) {
	writeError(w, http.StatusMethodNotAllowed, "method not allowed", "")
}
