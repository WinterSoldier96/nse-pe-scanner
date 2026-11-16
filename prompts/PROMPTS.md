# Claude Code prompts

**Episode 1 · Earnings or hype?** · Book 1: *Trade Like a Stock Market Wizard* (Mark Minervini), chapter 4 on P/E

These are the prompts used in the video, in order. Your results will differ: the AI writes slightly
different code each time, and NSE's data keeps growing. A Word copy is in
[`Claude_Code_prompts.docx`](Claude_Code_prompts.docx).

## Part 1 · Understand the raw data

### Prompt 1 · Read the raw files

> In this folder are two files I just downloaded from NSE's All Reports page: a PE Ratio file and a bhavcopy zip. Open both, explain every column in plain English, and tell me what "Symbol P/E" and "Adjusted P/E" could mean. Don't write any code yet.

## Part 2 · Fetch the history

### Prompt 2 · Find out how far back NSE goes

> NSE's All Reports page has an Archives tab where you pick a date. Work out how that page requests a file for a given date, and test which is the oldest date for which the PE Ratio file still exists. Try dates going back three years.

### Prompt 3 · Get NSE's trading days

> Don't find holidays by trial and error. NSE publishes its trading holidays on the "Market Timings & Holidays" page; find the data behind that page and use it to build the list of trading days from 30 April 2024 to today. Save the list, so we can still use it if NSE's site doesn't answer.

### Prompt 4 · Build the downloader

> Write fetch_nse.py that downloads the PE Ratio file and the bhavcopy for every day on that trading-day list, the same way the archive page requests them. Pause about a second between requests, never download a file twice, and print progress. NSE sometimes says "not found" for a file that exists, so retry once before giving up. If the new bhavcopy format is missing for a day before July 2024, fall back to the old "CM - Bhavcopy(csv)" format. Test it on the last 7 days first.

### Prompt 4b · Check the data is complete

> Write check_data.py: for every day on the trading-day list, confirm both files exist, open properly and have a normal number of stocks, and give me a completeness percentage and a list of anything missing.

## Part 3 · Build the scanner

### First, tell Claude where the data is

> The full history is now in data\pe and data\bhav.

(Use your own folder names. In this repository they are `PE File` and `bhav copy`.)

### Prompt 5 · The first scanner

> Write pe_scanner.py. Load all the PE files and bhavcopies. For every stock, work out EPS on each day as the closing price divided by the P/E. Find each stock's lowest price since 30 April 2024. Then work out the P/E expansion: today's P/E divided by the P/E on that low day. Also show how much of the price change came from earnings growth and how much came from the P/E changing. Adjust the prices for splits, bonuses and rights issues. Leave out loss-making stocks; illiquid stocks, meaning average daily trading below ₹1 crore; and stocks with fewer than 200 trading days of data. Tag a stock "Late stage" when its P/E has doubled, "Extreme" when it has tripled, and "Earnings-driven" when the P/E stayed roughly flat. Save the results to results.csv and show me the top 20 of each tag.

### Prompt 6 · Catch the AI's mistake

> Wait, let's check this list before we trust it. Remember how P/E works: it's the share price divided by the company's earnings per share. So a P/E can go up for two very different reasons. One: investors get excited and push the price up much faster than the profits grow. That is exactly what Minervini warns about. Two: the company's profits fall sharply while the price stays roughly where it was. The P/E still shoots up, but nobody got excited; the business just earned less. Those are not the same story, so don't mix them.
>
> Minervini's warning is about stocks that have made a big price move, but the book doesn't say how big. A computer needs a number, so we'll assume one: a big move means the price has risen at least 50% from its low. That's our assumption, not Minervini's, so mention it clearly in the results.
>
> Count a stock as P/E expansion only when its price has risen at least 50% from its low and its earnings have not fallen. Put the stocks whose P/E went up because profits collapsed into their own separate group, and label them clearly. Then show me the top of the late-stage list again.

### Prompt 7 · Test Minervini fairly

> Hold on, that test isn't fair. It measures each stock from the day its P/E was at its highest. But you only know a peak was the peak after it has passed. In real life, nobody could have sold on that day. That's hindsight, and it makes Minervini's warning look better than it really is.
>
> Let's test it the way an investor would actually live it. For each stock, find the first day its P/E had doubled from the low while the price was up at least 50%. That's the day the warning would first have shown up. From that day, measure what the stock did over the next 3 months and the next 6 months.
>
> On its own that number means nothing, because the whole market might have gone up or down in the same months. So compare it with a benchmark: the median return of all the stocks we analysed over exactly the same days. The median is the middle stock, so a few huge winners or losers can't distort it.
>
> Then do the same for the opposite case: stocks whose price also rose at least 50%, but whose P/E stayed roughly flat because the earnings grew along with the price. Show me both groups side by side: how many stocks, their median return, the market's return over the same days, and what share of them beat the market. Then we'll know whether hype-led rallies really did worse than earnings-led ones.

### Prompt 8 · Make it visual and check the work

> Now make this easy for anyone to understand, not just people who know charts. Build an interactive chart as a single web page I can open in my browser. It should be one file that works without the internet.
>
> Put every stock on it as a dot. Use colours for the groups: earnings-driven, late stage, extreme, profits collapsed and the rest. When I hover over a dot, show the stock name, its P/E at the low and today, how much the price rose and how much the earnings rose. Let me click a group to show or hide it. Add short, plain-English labels on the chart itself so a viewer understands it without me explaining: where the price grew in line with profits, where the price ran ahead of profits, and where profits ran ahead of the price. Add a search box so I can find any stock by name.
>
> Then check our results against what Minervini says in the book. He says that in his study of the biggest winners, the P/E typically rose two to three times from the start of the big move to its end. He also says a P/E that has doubled or tripled is a warning that the move may be late, not a sell signal by itself. Using only our NSE data, tell me:
>
> 1. Among the stocks that rose the most, did their P/E really rise about two to three times? Give me the median.
> 2. After the P/E had doubled, did those stocks do worse than the market, and by how much?
> 3. Where does our result agree with Minervini, and where does it not?
>
> Be honest about the differences between his study and ours: he looked at the biggest winners over many years in the US market, and we're looking at about two and a half years of NSE data. Put this comparison on the same page, below the chart, in plain language.
>
> Finally, check your own work: pick three stocks and compare today's P/E in our data with the P/E on NSE's own quote page.

## Part 4 · Make it usable by anyone

### Prompt 9 · One-click control panel

> Most viewers can't run Python commands, so make this usable with one click. Build a small web page that opens in the browser when someone double-clicks a file called START_HERE.bat. If Python's packages are missing, that file should install them first.
>
> The page needs four buttons, in order: download the last 7 days as a quick test, download everything, check the data is complete, and run the scanner. Show a live log of what's happening, a Stop button while something runs, and the number of NSE files downloaded with their date range.
>
> Keep the results hidden until a scan finishes. When it does, show them with the numbers counting up: how many stocks were analysed, and how many are extreme, late stage, earnings-driven and profits-collapsed, each with its share of the total. Let me click any of those boxes to see the list of stocks behind it. Below that, show the fair-test table, the chart, the top stocks in each group and links to the output files. If a scan was saved earlier, offer a "Show last scan" button with its date and time.
>
> Keep it safe: it must only work on this computer, only run our own scripts, and only open files in the output folder.

### Prompt 10 · Security check

> Do a security review of everything we wrote: the downloader, the scanner and the control panel. Look for anything that could run unexpected commands, read files outside the project, be reached from another computer or website, or leak anything. Fix what you find and list what you checked.
