"""Import the three selected nadir demo maps under the existing A-01 owner."""
import argparse
import asyncio
import shutil
import sys
from pathlib import Path

from sqlalchemy import select

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.database.session import AsyncSessionLocal, engine
from app.models.field import Field
from app.services.field_service import _geo_boundary

# Traced against the original 1536 x 1024 images, along the crop canopy edge.
MAPS = [
    ("02", "01", [
        [31,505],[43,454],[59,401],[82,357],[125,335],[181,312],
        [235,281],[280,249],[308,204],[336,156],[361,103],[407,62],
        [460,49],[516,64],[573,83],[627,97],[692,113],[764,117],
        [845,122],[925,116],[996,110],[1055,137],[1091,174],[1121,224],
        [1159,259],[1203,286],[1240,309],[1274,346],[1308,393],
        [1328,441],[1341,495],[1344,564],[1346,638],[1348,711],
        [1344,789],[1337,858],[1291,882],[1230,903],[1160,925],
        [1084,948],[1015,958],[947,952],[882,929],[816,910],
        [747,881],[683,854],[622,823],[557,799],[499,768],
        [442,732],[380,699],[317,665],[255,633],[195,604],
        [132,573],[75,549],[40,525],
    ]),
    ("03", "03", [
        [107,587],[110,538],[126,494],[159,447],[188,406],[221,355],
        [249,316],[273,288],[329,280],[392,275],[453,269],[517,260],
        [580,247],[645,231],[711,219],[779,203],[847,188],[911,171],
        [970,151],[1034,130],[1093,112],[1151,100],[1204,94],
        [1239,112],[1267,151],[1288,195],[1303,247],[1319,303],
        [1335,363],[1351,425],[1365,489],[1377,553],[1390,621],
        [1407,686],[1418,751],[1431,813],[1438,870],[1425,928],
        [1370,951],[1301,943],[1234,930],[1171,913],[1105,906],
        [1038,900],[970,894],[899,889],[832,887],[766,886],
        [699,883],[632,880],[565,874],[504,868],[445,855],
        [382,838],[326,819],[271,799],[218,778],[172,735],[135,659],
    ]),
    ("04", "04", [
        [128,79],[184,68],[245,62],[307,61],[369,74],[428,91],
        [489,113],[550,130],[610,144],[673,157],[738,169],[806,179],
        [876,188],[945,198],[1015,209],[1084,216],[1157,223],
        [1225,231],[1278,249],[1290,300],[1303,360],[1315,421],
        [1327,483],[1338,547],[1354,612],[1370,678],[1387,742],
        [1403,806],[1414,858],[1353,858],[1284,850],[1215,848],
        [1148,847],[1077,847],[1008,847],[942,847],[875,849],
        [809,848],[744,845],[681,832],[620,812],[561,791],
        [504,766],[451,742],[406,719],[365,696],[329,668],
        [299,625],[272,582],[249,544],[229,498],[213,455],
        [193,411],[180,365],[167,316],[153,267],[144,217],[136,166],[130,120],
    ]),
]


def contour(points):
    """Dense closed Catmull-Rom contour; no visual control markers needed."""
    output = []
    for i, p1 in enumerate(points):
        p0, p2, p3 = points[i - 1], points[(i + 1) % len(points)], points[(i + 2) % len(points)]
        for step in range(8):
            t = step / 8
            output.append([round(.5 * (2*p1[d] + (-p0[d]+p2[d])*t
                + (2*p0[d]-5*p1[d]+4*p2[d]-p3[d])*t*t
                + (-p0[d]+3*p1[d]-3*p2[d]+p3[d])*t*t*t), 2) for d in (0, 1)])
    return output + [output[0]]


async def seed(dry_run=False):
    async with AsyncSessionLocal() as db:
        original = await db.scalar(select(Field).where(Field.field_id == "FIELD_A01"))
        if original is None:
            raise RuntimeError("A-01 不存在，无法确认本次新增烟田的账号归属。")
        print("Using existing A-01 account owner:", original.owner_user_id)
        for number, asset, points in MAPS:
            field_id = "FIELD_A" + number
            row = await db.scalar(select(Field).where(Field.field_id == field_id))
            if row and row.owner_user_id != original.owner_user_id:
                raise RuntimeError("目标编号已属于其他用户：" + field_id)
            source = BACKEND_ROOT.parent / "frontend/src/assets/fields" / ("tobacco-field-nadir-" + asset + ".png")
            if not source.is_file():
                raise RuntimeError("缺少选定底图：" + str(source))
            boundary = contour(points)
            transform = {
                "method": "AFFINE_SIMULATED", "image_width": 1536, "image_height": 1024,
                "origin_longitude": round(113.13 + int(number)*.003, 6),
                "origin_latitude": round(23.46 + int(number)*.003, 6),
                "longitude_per_pixel": .000001, "latitude_per_pixel": -.0000008,
                "inverse": {"x": "(longitude-origin_longitude)/longitude_per_pixel",
                            "y": "(latitude-origin_latitude)/latitude_per_pixel"},
            }
            values = dict(owner_user_id=original.owner_user_id, name="演示烟田 A-" + number,
                description="垂直俯拍演示底图，边界沿烟草种植区轮廓描绘；WGS84 为模拟校准数据。",
                status="READY", data_source="DEMO_IMPORT", calibration_status="SIMULATED",
                coordinate_system="WGS84", base_map_path="storage/fields/demo-field-a" + number + ".png",
                pixel_boundary=boundary, geo_boundary=_geo_boundary(boundary, transform),
                control_points=[], transform_params=transform)
            if dry_run:
                print(field_id, "owner", original.owner_user_id, "contour points", len(boundary))
                continue
            if row is None:
                row = Field(field_id=field_id, version=1, **values)
                db.add(row)
            elif any(getattr(row, key) != value for key, value in values.items()):
                for key, value in values.items():
                    setattr(row, key, value)
                row.version += 1
            target = BACKEND_ROOT / values["base_map_path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                shutil.copy2(source, target)
            elif target.read_bytes() != source.read_bytes():
                raise RuntimeError("底图已存在且不同，保留原文件：" + str(target))
            print(field_id, "READY; version", row.version, "; contour points", len(boundary))
        if not dry_run:
            await db.commit()
            rows = (await db.execute(select(Field).where(
                Field.owner_user_id == original.owner_user_id
            ).order_by(Field.field_id))).scalars().all()
            print("Account fields:", [(item.field_id, item.status, item.version) for item in rows])


if __name__ == "__main__":
    engine.echo = False
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    asyncio.run(seed(parser.parse_args().dry_run))
