import oracledb, json

conn = oracledb.connect(user='ADMIN', password='${ADB_PASS}', dsn='${ADB_DSN}', config_dir='/path/to/wallet', wallet_location='/path/to/wallet', wallet_password='${ADB_WALLET_PASSWORD}')
cur = conn.cursor()

cur.execute("SELECT VM_NAME, POWERSTATE, DNS_NAME, CLUSTER_NAME, PRIMARY_IP, APPLICATION, CPUS, MEMORY_MB, TOTAL_DISK_MIB, OS_CONFIG, MIGRATION_TARGET, MIGRATION_WAVE, DATACENTER, HOST_NAME, VM_CRITICALITY, VM_ENVIRONMENT FROM RVTOOLS_VINFO ORDER BY CLUSTER_NAME, VM_NAME")
cols = [c[0] for c in cur.description]
vms = [dict(zip(cols,r)) for r in cur.fetchall()]
print("VMs:", len(vms))

cur.execute("SELECT * FROM APP_MIGRATION_PLAN")
cols2 = [c[0] for c in cur.description]
mp = [dict(zip(cols2,r)) for r in cur.fetchall()]
print("Migration plan:", len(mp))

cur.execute("SELECT * FROM APP_INVENTORY")
cols3 = [c[0] for c in cur.description]
apps = [dict(zip(cols3,r)) for r in cur.fetchall()]
print("Apps:", len(apps))

with open('/home/opc/inventory_vms.json','w') as f:
    json.dump(vms, f, default=str)
with open('/home/opc/migration_plan.json','w') as f:
    json.dump(mp, f, default=str)
with open('/home/opc/app_inventory.json','w') as f:
    json.dump(apps, f, default=str)

print("Sizes:", len(json.dumps(vms,default=str)), len(json.dumps(mp,default=str)), len(json.dumps(apps,default=str)))
conn.close()
print("Done")
