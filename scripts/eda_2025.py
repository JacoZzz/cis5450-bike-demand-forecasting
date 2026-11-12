"""Generate the four January–July 2025 check-in figures."""
from pathlib import Path
import os
import csv
import duckdb
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

os.chdir(Path(__file__).resolve().parents[1])
out = Path("eda")
out.mkdir(exist_ok=True)
db = duckdb.connect()
db.execute("""create view panel as select *,hour(hour_local) h,
    isodow(hour_local)<=5 weekday from 'data/clean/station_hour_clean.parquet'
    where eligible_at_hour_start and hour_local >= '2025-01-01' and hour_local < '2025-08-01'""")
db.execute("""create view trips as select * from 'data/clean/trips_clean.parquet'
    where started_at >= '2025-01-01' and started_at < '2025-08-01'""")

def query(name, sql):
    result = db.execute(sql)
    rows = result.fetchall()
    with (out / (name + ".csv")).open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([c[0] for c in result.description])
        writer.writerows(rows)
    return rows

def save(name):
    plt.savefig(out / (name + ".png"), dpi=180, bbox_inches="tight")
    plt.close()

plt.rcParams.update({"axes.spines.top":False,"axes.spines.right":False,"axes.titlelocation":"left",
                     "axes.titleweight":"bold","font.size":10,"figure.constrained_layout.use":True})
a = query("A_hourly_departures", """select weekday,h,count(*) station_hours,avg(departures) mean_departures
 from panel group by all order by weekday,h""")
fig, ax = plt.subplots(figsize=(8,4))
for flag,label,color in [(True,"Weekday","#196486"),(False,"Weekend","#b75223")]:
    subset = [r for r in a if r[0]==flag]
    assert len(subset)==24
    ax.plot([r[1] for r in subset],[r[3] for r in subset],label=label,color=color,lw=2.5)
    print(label,max(subset,key=lambda r:r[3]),subset[8])
ax.set(title="Hourly bike departures on weekdays and weekends",xlabel="New York local hour",ylabel="Mean departures per eligible station-hour",xticks=range(0,24,2),ylim=(0,None))
ax.legend(frameon=False)
save("A_hourly_departures")

b = query("B_station_net_outflow", """with top as (select station_id,sum(arrivals+departures) volume
 from panel group by 1 order by volume desc,station_id limit 10),
 names as (select start_station_id station_id,mode(start_station_name order by start_station_name) name
 from trips where start_station_id in (select station_id from top) group by 1)
 select station_id,name,volume,h,count(*) weekday_hours,avg(departures-arrivals) net
 from panel join top using(station_id) left join names using(station_id)
 where weekday group by all order by volume desc,station_id,h""")
assert len(b)==240
matrix=np.array([r[-1] for r in b]).reshape(10,24)
fig,ax=plt.subplots(figsize=(11,5))
limit=np.max(abs(matrix))
im=ax.imshow(matrix,cmap="RdBu_r",aspect="auto",vmin=-limit,vmax=limit)
ax.set(yticks=range(10),yticklabels=[r[1] or r[0] for r in b[::24]],xticks=range(0,24,2),
       xlabel="New York local hour",title="Weekday net outflow at the 10 busiest stations")
fig.colorbar(im,ax=ax,label="Mean departures minus arrivals per hour")
save("B_station_net_outflow")
for row in b[::24][:3]:
    print(row[1],[(r[3],round(r[-1],2)) for r in b if r[0]==row[0] and r[3] in (8,17)])

c=query("C_electric_share","""select member_casual,count(*) rides,countif(rideable_type='electric_bike') electric,
 avg((rideable_type='electric_bike')::int) share from trips group by 1 order by 1""")
print(c)
fig,ax=plt.subplots(figsize=(7,4))
for i,(category,n,e,share) in enumerate(c):
    ax.bar(i,100*share,color=["#ba6739","#196486"][i],width=.52)
    ax.text(i,100*share+2,f"{share:.1%}\n{n:,} rides",ha="center")
ax.set(xticks=[0,1],xticklabels=[r[0].title() for r in c],ylim=(0,100),ylabel="Electric-bike rides (%)",
       title="Electric-bike share within each rider group")
save("C_electric_share")

d=query("D_station_zero_share","""select station_id,count(*) eligible_hours,countif(inferred_zero) zero_hours,
 avg(inferred_zero::int) zero_share from panel group by 1 order by 1""")
assert sum(r[1] for r in d)==sum(r[2] for r in a)
shares=np.array([r[-1]*100 for r in d])
print("D",len(d),sum(r[1] for r in d),sum(r[2] for r in d),np.percentile(shares,[25,50,75]),sum(r[1]<24 for r in d))
fig,ax=plt.subplots(figsize=(8,4))
ax.hist(shares,bins=np.arange(0,105,5),color="#367c75",edgecolor="white")
median=np.median(shares)
ax.axvline(median,ls="--",color="#343434",label=f"Station median: {median:.1f}%")
ax.set(title="How often do eligible stations record zero flow?",xlabel="Eligible hours with no departures or arrivals (%)",
       ylabel="Number of stations",xlim=(0,100))
ax.legend(frameon=False)
save("D_station_zero_share")
