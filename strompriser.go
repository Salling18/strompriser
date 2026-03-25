package main

import (
	"encoding/json"
	"fmt"
	"io"
	"math"
	"net/http"
	"net/url"
	"os"
	"sort"
	"strings"
	"time"
)

const (
	reset  = "\033[0m"
	bold   = "\033[1m"
	dim    = "\033[2m"
	cyan   = "\033[96m"
	green  = "\033[92m"
	yellow = "\033[93m"
	red    = "\033[91m"
)

const moms = 0.25 // spot fra API er ekskl. moms; NRGI-tariffer er inkl. moms

// NRGI samlede afgifter pr. time (inkl. elafgift og moms), indeks = time 0–23
var tariffs = [24]float64{
	0.21, 0.21, 0.21, 0.21, 0.21, 0.21, // 00–05
	0.34, 0.34, 0.34, 0.34, 0.34, 0.34, 0.34, 0.34, 0.34, 0.34, 0.34, // 06–16
	0.70, 0.70, 0.70, 0.70, // 17–20
	0.34, 0.34, 0.34, // 21–23
}

var (
	apiFilter = url.QueryEscape(`{"PriceArea":"DK1"}`)
	apiSort   = strings.ReplaceAll(url.QueryEscape("TimeDK asc"), "+", "%20")
)

type record struct {
	TimeDK           string   `json:"TimeDK"`
	DayAheadPriceDKK *float64 `json:"DayAheadPriceDKK"`
}

func fetchPrices(start, end time.Time) ([]record, error) {
	days := int(end.Sub(start).Hours()/24) + 1
	rawURL := fmt.Sprintf(
		"https://api.energidataservice.dk/dataset/DayAheadPrices"+
			"?start=%s&end=%s&filter=%s&sort=%s&limit=%d",
		start.Format("2006-01-02"),
		end.AddDate(0, 0, 1).Format("2006-01-02"),
		apiFilter, apiSort, days*96,
	)
	resp, err := http.Get(rawURL)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, err
	}
	var data struct {
		Records []record `json:"records"`
	}
	return data.Records, json.Unmarshal(body, &data)
}

func spotDKK(r record) float64 {
	if r.DayAheadPriceDKK == nil {
		return 0
	}
	return *r.DayAheadPriceDKK / 1000
}

func medAfgifter(spot float64, hour int) float64 {
	return spot*(1+moms) + tariffs[hour]
}

type hourPrice struct {
	hour  int
	price float64
}

func aggregateHourly(records []record) []hourPrice {
	buckets := map[int][]float64{}
	for _, r := range records {
		h := int(r.TimeDK[11]-'0')*10 + int(r.TimeDK[12]-'0')
		buckets[h] = append(buckets[h], spotDKK(r))
	}
	keys := make([]int, 0, len(buckets))
	for h := range buckets {
		keys = append(keys, h)
	}
	sort.Ints(keys)
	out := make([]hourPrice, len(keys))
	for i, h := range keys {
		v := buckets[h]
		sum := 0.0
		for _, x := range v {
			sum += x
		}
		out[i] = hourPrice{h, sum / float64(len(v))}
	}
	return out
}

func priceColor(p, lo, hi float64) string {
	if hi == lo {
		return green
	}
	t := (p - lo) / (hi - lo)
	switch {
	case t < 0.33:
		return green
	case t < 0.66:
		return yellow
	default:
		return red
	}
}

func drawBar(p, lo, hi float64) string {
	const width = 14
	var filled int
	if hi == lo {
		filled = width
	} else {
		filled = int(math.Round((p - lo) / (hi - lo) * float64(width)))
	}
	return strings.Repeat("█", filled) + dim + strings.Repeat("░", width-filled) + reset
}

func fmtP(p float64) string {
	return fmt.Sprintf("%.2f kr", p)
}

func recordsFor(records []record, d time.Time) []record {
	prefix := d.Format("2006-01-02")
	var out []record
	for _, r := range records {
		if strings.HasPrefix(r.TimeDK, prefix) {
			out = append(out, r)
		}
	}
	return out
}

func printDay(records []record, label string, isToday bool) {
	if len(records) == 0 {
		fmt.Printf("\n%s  Ingen data for %s%s\n", dim, label, reset)
		return
	}

	hourly := aggregateHourly(records)
	prices := make([]float64, len(hourly))
	totals := make([]float64, len(hourly))
	for i, h := range hourly {
		prices[i] = h.price * (1 + moms)
		totals[i] = medAfgifter(h.price, h.hour)
	}

	lo, hi := totals[0], totals[0]
	minSpot, maxSpot := prices[0], prices[0]
	sumSpot, sumTotal := 0.0, 0.0
	for i, t := range totals {
		if t < lo {
			lo = t
		}
		if t > hi {
			hi = t
		}
		if prices[i] < minSpot {
			minSpot = prices[i]
		}
		if prices[i] > maxSpot {
			maxSpot = prices[i]
		}
		sumSpot += prices[i]
		sumTotal += t
	}
	avgSpot := sumSpot / float64(len(prices))
	avgTotal := sumTotal / float64(len(totals))

	nowHour := -1
	if isToday {
		nowHour = time.Now().Hour()
	}

	sep := strings.Repeat("─", 62)
	fmt.Printf("\n%s%s%s%s\n", bold, cyan, sep, reset)
	fmt.Printf("%s%s  %-30s  DK1 · kr/kWh%s\n", bold, cyan, strings.ToUpper(label), reset)
	fmt.Printf("%s%s%s%s\n", bold, cyan, sep, reset)
	fmt.Printf("  %s%6s%7s  %7s  %7s%s\n", dim, "", "min", "avg", "max", reset)
	fmt.Printf("  %sspot:  %s%s%7s%s  %s%7s%s  %s%7s%s\n",
		dim, reset,
		green, fmtP(minSpot), reset,
		yellow, fmtP(avgSpot), reset,
		red, fmtP(maxSpot), reset)
	fmt.Printf("  %stotal: %s%s%7s%s  %s%7s%s  %s%7s%s\n",
		dim, reset,
		green, fmtP(lo), reset,
		yellow, fmtP(avgTotal), reset,
		red, fmtP(hi), reset)
	fmt.Printf("%s%s%s\n", dim, sep, reset)

	for i, hp := range hourly {
		total := totals[i]
		color := priceColor(total, lo, hi)
		rb, marker := "", " "
		if hp.hour == nowHour {
			rb = bold
			marker = bold + " " + reset
		}
		fmt.Printf("  %s%s%02d:00%s  %s%s%s  %s%7s  %s→%s  %s%s%7s%s %s\n",
			rb, dim, hp.hour, reset,
			color, drawBar(total, lo, hi), reset,
			rb, fmtP(prices[i]),
			dim, reset,
			rb, color, fmtP(total), reset,
			marker)
	}
	fmt.Printf("%s%s%s\n", dim, sep, reset)
}

func main() {
	showTomorrow := len(os.Args) > 1 &&
		(os.Args[1] == "tomorrow" || os.Args[1] == "all")

	today := time.Now().Truncate(24 * time.Hour)
	end := today
	if showTomorrow {
		end = today.AddDate(0, 0, 1)
	}

	fmt.Printf("\n%sStrømpris · Vestdanmark (DK1)%s\n", bold, reset)
	fmt.Printf("%sKilde: Energi Data Service%s\n", dim, reset)

	records, err := fetchPrices(today, end)
	if err != nil {
		fmt.Fprintf(os.Stderr, "\n%sFejl: %v%s\n", red, err, reset)
		os.Exit(1)
	}

	printDay(recordsFor(records, today), "I dag", true)
	if showTomorrow {
		printDay(recordsFor(records, end), "I morgen", false)
	}
	fmt.Println()
}
