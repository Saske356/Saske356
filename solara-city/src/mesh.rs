//! Mesh builder: merges many primitives into one mesh per material to keep
//! draw calls low (the main performance trick of the whole city).
use bevy::asset::RenderAssetUsages;
use bevy::prelude::*;
use bevy::render::mesh::{Indices, PrimitiveTopology, VertexAttributeValues};

#[derive(Default, Clone)]
pub struct Mb {
    pub pos: Vec<[f32; 3]>,
    pub nrm: Vec<[f32; 3]>,
    pub uv: Vec<[f32; 2]>,
    pub idx: Vec<u32>,
}

impl Mb {
    pub fn is_empty(&self) -> bool {
        self.idx.is_empty()
    }

    pub fn add_mesh(&mut self, mesh: &Mesh, t: Transform) {
        let m = t.compute_matrix();
        let nm = Mat3::from_mat4(m).inverse().transpose();
        let base = self.pos.len() as u32;
        let Some(VertexAttributeValues::Float32x3(p)) = mesh.attribute(Mesh::ATTRIBUTE_POSITION) else {
            return;
        };
        let n: Vec<[f32; 3]> = match mesh.attribute(Mesh::ATTRIBUTE_NORMAL) {
            Some(VertexAttributeValues::Float32x3(n)) => n.clone(),
            _ => vec![[0., 1., 0.]; p.len()],
        };
        let uv: Vec<[f32; 2]> = match mesh.attribute(Mesh::ATTRIBUTE_UV_0) {
            Some(VertexAttributeValues::Float32x2(u)) => u.clone(),
            _ => vec![[0., 0.]; p.len()],
        };
        for i in 0..p.len() {
            self.pos.push(m.transform_point3(Vec3::from(p[i])).into());
            self.nrm.push((nm * Vec3::from(n[i])).normalize_or_zero().into());
            self.uv.push(uv[i]);
        }
        let start = self.idx.len();
        match mesh.indices() {
            Some(Indices::U32(ix)) => self.idx.extend(ix.iter().map(|i| i + base)),
            Some(Indices::U16(ix)) => self.idx.extend(ix.iter().map(|i| *i as u32 + base)),
            None => self.idx.extend((0..p.len() as u32).map(|i| i + base)),
        }
        if m.determinant() < 0.0 {
            for tri in self.idx[start..].chunks_mut(3) {
                tri.swap(1, 2);
            }
        }
    }

    pub fn cuboid(&mut self, c: Vec3, size: Vec3, rot: Quat) {
        self.add_mesh(
            &Mesh::from(Cuboid::from_size(size)),
            Transform::from_translation(c).with_rotation(rot),
        );
    }
    pub fn bx(&mut self, c: Vec3, size: Vec3) {
        self.cuboid(c, size, Quat::IDENTITY);
    }
    /// Box spanning from a to b with the given cross-section.
    pub fn seg(&mut self, a: Vec3, b: Vec3, w: f32, h: f32) {
        let d = b - a;
        let len = d.length();
        if len < 1e-5 {
            return;
        }
        let rot = Quat::from_rotation_arc(Vec3::Z, d / len);
        self.cuboid((a + b) * 0.5, Vec3::new(w, h, len), rot);
    }
    /// Tapered cylinder from a (radius r0) to b (radius r1).
    pub fn cyl_seg(&mut self, a: Vec3, b: Vec3, r0: f32, r1: f32, res: u32) {
        let d = b - a;
        let len = d.length();
        if len < 1e-5 {
            return;
        }
        let mesh = ConicalFrustum { radius_top: r1, radius_bottom: r0, height: len }
            .mesh()
            .resolution(res)
            .build();
        let rot = Quat::from_rotation_arc(Vec3::Y, d / len);
        self.add_mesh(&mesh, Transform::from_translation((a + b) * 0.5).with_rotation(rot));
    }
    pub fn cyl(&mut self, c: Vec3, r: f32, h: f32, res: u32, rot: Quat) {
        let mesh = Cylinder::new(r, h).mesh().resolution(res).build();
        self.add_mesh(&mesh, Transform::from_translation(c).with_rotation(rot));
    }
    pub fn sphere(&mut self, c: Vec3, scale: Vec3, rot: Quat, res: u32) {
        let mesh = Sphere::new(1.0).mesh().uv(res * 2, res);
        self.add_mesh(&mesh, Transform::from_translation(c).with_rotation(rot).with_scale(scale));
    }
    pub fn torus(&mut self, c: Vec3, major: f32, minor: f32, rot: Quat, scale: Vec3) {
        let mesh = Torus { minor_radius: minor, major_radius: major }
            .mesh()
            .minor_resolution(12)
            .major_resolution(36)
            .build();
        self.add_mesh(&mesh, Transform::from_translation(c).with_rotation(rot).with_scale(scale));
    }

    fn push_v(&mut self, p: Vec3, n: Vec3, uv: Vec2) -> u32 {
        self.pos.push(p.into());
        self.nrm.push(n.into());
        self.uv.push(uv.into());
        (self.pos.len() - 1) as u32
    }

    pub fn tri(&mut self, a: Vec3, b: Vec3, c: Vec3) {
        let n = (b - a).cross(c - a).normalize_or_zero();
        let i0 = self.push_v(a, n, Vec2::ZERO);
        let i1 = self.push_v(b, n, Vec2::ZERO);
        let i2 = self.push_v(c, n, Vec2::ZERO);
        self.idx.extend([i0, i1, i2]);
    }

    /// Quad with per-vertex normals; winding is fixed automatically to match the normals.
    pub fn quad_n(&mut self, p: [Vec3; 4], n: [Vec3; 4], uv: [Vec2; 4]) {
        let face = (p[1] - p[0]).cross(p[2] - p[0]) + (p[2] - p[0]).cross(p[3] - p[0]);
        let navg = n[0] + n[1] + n[2] + n[3];
        let order: [usize; 4] = if face.dot(navg) >= 0.0 { [0, 1, 2, 3] } else { [0, 3, 2, 1] };
        let b = self.pos.len() as u32;
        for k in order {
            self.push_v(p[k], n[k], uv[k]);
        }
        self.idx.extend([b, b + 1, b + 2, b, b + 2, b + 3]);
    }

    pub fn quad_uv(&mut self, a: Vec3, b: Vec3, c: Vec3, d: Vec3, uv: [Vec2; 4]) {
        let n = ((b - a).cross(c - a) + (c - a).cross(d - a)).normalize_or_zero();
        self.quad_n([a, b, c, d], [n; 4], uv);
    }

    /// Triangle fan around a centre, oriented so the face normal points along `hint`.
    pub fn fan(&mut self, center: Vec3, pts: &[Vec3], hint: Vec3) {
        let n = hint.normalize_or_zero();
        for k in 0..pts.len() {
            let a = pts[k];
            let b = pts[(k + 1) % pts.len()];
            let f = (a - center).cross(b - center);
            let (p1, p2) = if f.dot(n) >= 0.0 { (a, b) } else { (b, a) };
            let i0 = self.push_v(center, n, Vec2::ZERO);
            let i1 = self.push_v(p1, n, Vec2::ZERO);
            let i2 = self.push_v(p2, n, Vec2::ZERO);
            self.idx.extend([i0, i1, i2]);
        }
    }

    /// Axis-aligned box with world-space UVs (u = horizontal metres / tile.x, v = -height / tile.y).
    pub fn box_uv(&mut self, mn: Vec3, mx: Vec3, tile: Vec2, top: bool) {
        let v = |y: f32| -y / tile.y;
        let uvs = |h0: f32, h1: f32, y0: f32, y1: f32| {
            [
                Vec2::new(h0 / tile.x, v(y0)),
                Vec2::new(h1 / tile.x, v(y0)),
                Vec2::new(h1 / tile.x, v(y1)),
                Vec2::new(h0 / tile.x, v(y1)),
            ]
        };
        // +X
        self.quad_uv(
            Vec3::new(mx.x, mn.y, mx.z),
            Vec3::new(mx.x, mn.y, mn.z),
            Vec3::new(mx.x, mx.y, mn.z),
            Vec3::new(mx.x, mx.y, mx.z),
            uvs(-mx.z, -mn.z, mn.y, mx.y),
        );
        // -X
        self.quad_uv(
            Vec3::new(mn.x, mn.y, mn.z),
            Vec3::new(mn.x, mn.y, mx.z),
            Vec3::new(mn.x, mx.y, mx.z),
            Vec3::new(mn.x, mx.y, mn.z),
            uvs(mn.z, mx.z, mn.y, mx.y),
        );
        // +Z
        self.quad_uv(
            Vec3::new(mn.x, mn.y, mx.z),
            Vec3::new(mx.x, mn.y, mx.z),
            Vec3::new(mx.x, mx.y, mx.z),
            Vec3::new(mn.x, mx.y, mx.z),
            uvs(mn.x, mx.x, mn.y, mx.y),
        );
        // -Z
        self.quad_uv(
            Vec3::new(mx.x, mn.y, mn.z),
            Vec3::new(mn.x, mn.y, mn.z),
            Vec3::new(mn.x, mx.y, mn.z),
            Vec3::new(mx.x, mx.y, mn.z),
            uvs(-mx.x, -mn.x, mn.y, mx.y),
        );
        if top {
            self.quad_uv(
                Vec3::new(mn.x, mx.y, mx.z),
                Vec3::new(mx.x, mx.y, mx.z),
                Vec3::new(mx.x, mx.y, mn.z),
                Vec3::new(mn.x, mx.y, mn.z),
                [
                    Vec2::new(mn.x / tile.x, mx.z / tile.x),
                    Vec2::new(mx.x / tile.x, mx.z / tile.x),
                    Vec2::new(mx.x / tile.x, mn.z / tile.x),
                    Vec2::new(mn.x / tile.x, mn.z / tile.x),
                ],
            );
        }
    }

    /// Horizontal quad with world UVs.
    pub fn ground(&mut self, mn: Vec2, mx: Vec2, y: f32, tile: f32) {
        self.quad_uv(
            Vec3::new(mn.x, y, mx.y),
            Vec3::new(mx.x, y, mx.y),
            Vec3::new(mx.x, y, mn.y),
            Vec3::new(mn.x, y, mn.y),
            [
                Vec2::new(mn.x / tile, mx.y / tile),
                Vec2::new(mx.x / tile, mx.y / tile),
                Vec2::new(mx.x / tile, mn.y / tile),
                Vec2::new(mn.x / tile, mn.y / tile),
            ],
        );
    }

    /// Vertical cylinder wall with world UVs, smooth normals, optional top cap.
    pub fn cyl_uv(&mut self, c: Vec3, r: f32, h: f32, segs: u32, tile: Vec2, cap: bool) {
        let circ = std::f32::consts::TAU * r;
        let tx = (circ / tile.x).round().max(1.0); // integer repeats so the seam matches
        for i in 0..segs {
            let a0 = i as f32 / segs as f32 * std::f32::consts::TAU;
            let a1 = (i + 1) as f32 / segs as f32 * std::f32::consts::TAU;
            let n0 = Vec3::new(a0.cos(), 0.0, a0.sin());
            let n1 = Vec3::new(a1.cos(), 0.0, a1.sin());
            let u0 = i as f32 / segs as f32 * tx;
            let u1 = (i + 1) as f32 / segs as f32 * tx;
            let y0 = c.y;
            let y1 = c.y + h;
            self.quad_n(
                [c + n1 * r, c + n0 * r, c + n0 * r + Vec3::Y * h, c + n1 * r + Vec3::Y * h],
                [n1, n0, n0, n1],
                [
                    Vec2::new(u1, -y0 / tile.y),
                    Vec2::new(u0, -y0 / tile.y),
                    Vec2::new(u0, -y1 / tile.y),
                    Vec2::new(u1, -y1 / tile.y),
                ],
            );
        }
        if cap {
            let pts: Vec<Vec3> = (0..segs)
                .map(|i| {
                    let a = i as f32 / segs as f32 * std::f32::consts::TAU;
                    c + Vec3::new(a.cos() * r, h, a.sin() * r)
                })
                .collect();
            self.fan(c + Vec3::Y * h, &pts, Vec3::Y);
        }
    }

    pub fn translate(&mut self, off: Vec3) {
        for p in &mut self.pos {
            p[0] += off.x;
            p[1] += off.y;
            p[2] += off.z;
        }
    }

    pub fn build(&self) -> Mesh {
        Mesh::new(PrimitiveTopology::TriangleList, RenderAssetUsages::default())
            .with_inserted_attribute(Mesh::ATTRIBUTE_POSITION, self.pos.clone())
            .with_inserted_attribute(Mesh::ATTRIBUTE_NORMAL, self.nrm.clone())
            .with_inserted_attribute(Mesh::ATTRIBUTE_UV_0, self.uv.clone())
            .with_inserted_indices(Indices::U32(self.idx.clone()))
    }
}

/// Loft a grid of rings into quads. Normals come from finite differences and
/// are oriented away from each ring's centroid. `emit` receives each quad.
pub fn loft(rings: &[Vec<Vec3>], closed: bool, mut emit: impl FnMut([Vec3; 4], [Vec3; 4])) {
    let ni = rings.len();
    if ni < 2 {
        return;
    }
    let m = rings[0].len();
    let cents: Vec<Vec3> = rings
        .iter()
        .map(|r| r.iter().copied().sum::<Vec3>() / r.len() as f32)
        .collect();
    let mut nrm = vec![vec![Vec3::Y; m]; ni];
    for i in 0..ni {
        for j in 0..m {
            let jp = if closed { (j + 1) % m } else { (j + 1).min(m - 1) };
            let jm = if closed { (j + m - 1) % m } else { j.saturating_sub(1) };
            let ip = (i + 1).min(ni - 1);
            let im = i.saturating_sub(1);
            let tj = rings[i][jp] - rings[i][jm];
            let ti = rings[ip][j] - rings[im][j];
            let mut n = tj.cross(ti).normalize_or_zero();
            let out = rings[i][j] - cents[i];
            if n == Vec3::ZERO {
                n = out.normalize_or_zero();
            } else if n.dot(out) < 0.0 {
                n = -n;
            }
            nrm[i][j] = n;
        }
    }
    let jn = if closed { m } else { m - 1 };
    for i in 0..ni - 1 {
        for j in 0..jn {
            let j1 = (j + 1) % m;
            emit(
                [rings[i][j], rings[i][j1], rings[i + 1][j1], rings[i + 1][j]],
                [nrm[i][j], nrm[i][j1], nrm[i + 1][j1], nrm[i + 1][j]],
            );
        }
    }
}
